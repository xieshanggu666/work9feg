from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Exam, ExamAttempt, ExamAnswer, ExamQuestion, Question, QuestionOption,
)
from app.schemas.attempt import AnswerSubmit, ExamSubmitRequest
from app.services import booking_service


def _collect_exam_questions(db: Session, exam: Exam):
    """获取考试题目，支持乱序"""
    eqs = exam.questions
    if exam.is_random_order:
        eqs = sorted(eqs, key=lambda x: id(x) % 997)  # 伪随机，仅演示
    result = []
    for eq in eqs:
        question = db.query(Question).filter(Question.id == eq.question_id).first()
        if not question:
            continue
        options = [
            {"id": opt.id, "content": opt.content, "order_index": opt.order_index}
            for opt in question.options
        ]
        result.append({
            "exam_question_id": eq.id,
            "question_id": question.id,
            "question_type": question.question_type,
            "content": question.content,
            "score": eq.score,
            "options": options,
        })
    return result


def start_exam(db: Session, exam: Exam, user_id: int, ip: str, user_agent: str) -> ExamAttempt:
    """开始考试。

    开考资格与次数由预约模块驱动：
    - 进行中的考试直接返回原记录；
    - 无需预约的考试受 max_attempts 限制；
    - 需预约的考试必须存在已通过、在时段窗口内且场次匹配的预约，
      开考成功后预约标记为 used。
    """
    existing = (
        db.query(ExamAttempt)
        .filter(
            ExamAttempt.exam_id == exam.id,
            ExamAttempt.user_id == user_id,
            ExamAttempt.status == "in_progress",
        )
        .first()
    )
    if existing:
        return existing

    eligibility = booking_service.check_eligibility(db, exam, user_id)
    if not eligibility["can_start"]:
        raise ValueError(eligibility["reason"] or "当前不满足开考条件")

    used = eligibility["used_attempts"]
    attempt_no = used + 1
    booking = eligibility["booking"]
    booking_id = booking.id if booking else None
    if booking and booking.status == "approved":
        attempt_no = booking.attempt_no

    attempt = ExamAttempt(
        exam_id=exam.id,
        user_id=user_id,
        booking_id=booking_id,
        attempt_no=attempt_no,
        ip_address=ip,
        user_agent=user_agent[:255],
    )
    db.add(attempt)
    db.flush()
    if booking and booking.status == "approved":
        booking_service.consume_booking(db, booking)
    db.commit()
    db.refresh(attempt)
    return attempt


def submit_exam(db: Session, attempt: ExamAttempt, data: ExamSubmitRequest) -> ExamAttempt:
    exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
    if not exam:
        raise ValueError("考试不存在")

    now = datetime.now()
    deadline = attempt.start_time + timedelta(minutes=exam.duration_minutes)
    if now > deadline:
        raise ValueError("考试已超时，无法提交")

    # 逐题评分
    question_map = {
        eq.question_id: eq.score
        for eq in db.query(ExamQuestion).filter(ExamQuestion.exam_id == exam.id).all()
    }
    total_score = 0.0
    for answer in data.answers:
        question = db.query(Question).filter(Question.id == answer.question_id).first()
        if not question:
            continue
        full_score = float(question_map.get(question.id, 5))
        correct, got_score = _grade_answer(question, answer, full_score)
        total_score += got_score
        db.add(ExamAnswer(
            attempt_id=attempt.id,
            question_id=question.id,
            user_answer=answer.user_answer,
            is_correct=1 if correct else 0,
            score=got_score,
            time_spent_seconds=answer.time_spent_seconds,
        ))

    attempt.score = round(total_score, 1)
    attempt.submit_time = datetime.now()
    attempt.status = "graded"
    attempt.is_passed = 1 if attempt.score >= exam.pass_score else 0
    db.commit()
    db.refresh(attempt)

    # 预约/补考联动：通过考试后自动发放证书（已持证书则更新更高成绩）
    from app.services import grade_service
    grade_service.auto_issue_certificate(db, attempt)
    return attempt


def _normalize_answer(s: str) -> str:
    return s.strip().lower()


def _grade_answer(question: Question, answer: AnswerSubmit,
                  full_score: float = 5.0) -> tuple[bool, float]:
    """
    自动评分（full_score 为该题在试卷中的分值，默认 5 分）：
    - 单选/判断：答案匹配正确选项 ID
    - 多选：全对得满分；漏选给部分分；错选不得分
    - 填空：与标准答案匹配（多个答案用 | 分隔）
    - 简答/编程：关键词命中（简答按关键词比例给分，编程标记待人工）
    """
    qtype = question.question_type
    user_ans = _normalize_answer(answer.user_answer)

    if qtype in ("single_choice", "judgment"):
        correct_ids = {
            str(opt.id) for opt in question.options if opt.is_correct == 1
        }
        return (user_ans in correct_ids, full_score if user_ans in correct_ids else 0.0)

    elif qtype == "multiple_choice":
        correct_ids = {
            str(opt.id) for opt in question.options if opt.is_correct == 1
        }
        user_set = {x.strip() for x in user_ans.split(",") if x.strip()}
        if not user_set:
            return (False, 0.0)
        hit = len(user_set & correct_ids)
        if hit == len(correct_ids) and len(user_set) == len(correct_ids):
            return (True, full_score)
        ratio = hit / len(correct_ids)
        return (False, round(full_score * ratio, 1))

    elif qtype == "fill_blank":
        standards = [s.strip().lower() for s in question.analysis.split("|") if s.strip()]
        if not standards:
            return (False, 0.0)
        return (user_ans in standards, full_score if user_ans in standards else 0.0)

    elif qtype == "short_answer":
        keywords = [k.strip().lower() for k in question.analysis.split("|") if k.strip()]
        if not keywords:
            return (False, 0.0)
        hit = sum(1 for k in keywords if k in user_ans)
        ratio = hit / len(keywords)
        return (ratio >= 0.5, round(full_score * ratio, 1))

    elif qtype == "programming":
        # 编程题需人工评测，此处不自动给分
        return (False, 0.0)

    return (False, 0.0)


def get_attempt(db: Session, attempt_id: int) -> ExamAttempt | None:
    return db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()


def get_user_attempts(db: Session, user_id: int, page: int = 1, page_size: int = 10):
    query = db.query(ExamAttempt).filter(ExamAttempt.user_id == user_id)
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return total, items


def get_attempt_result(db: Session, attempt: ExamAttempt):
    answers = db.query(ExamAnswer).filter(ExamAnswer.attempt_id == attempt.id).all()
    return answers
