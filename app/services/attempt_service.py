from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Exam, ExamAttempt, ExamAnswer, ExamQuestion, Question,
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


def get_deadline(attempt: ExamAttempt, exam: Exam) -> datetime:
    """交卷截止时刻 = 开考时间 + 考试时长（以服务端时钟为准）"""
    return attempt.start_time + timedelta(minutes=exam.duration_minutes)


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


# ---------- 自动保存（草稿） ----------
def get_saved_answers(db: Session, attempt: ExamAttempt) -> list[ExamAnswer]:
    """读取已保存的答案（交卷前为草稿，交卷后为最终答案）。"""
    return db.query(ExamAnswer).filter(ExamAnswer.attempt_id == attempt.id).all()


def save_answers(db: Session, attempt: ExamAttempt, data: AnswerSaveRequest,
                 _retry: int = 0) -> dict:
    """把客户端答案增量保存到服务端（upsert），供刷新/重连恢复与到时自动交卷。

    多端冲突策略（字段级）：每题携带 base_version（客户端上次同步到的版本）。
    若服务端该题版本比 base_version 新，说明另一设备已更新过此题——
    本次写入不覆盖服务端（server-wins，避免静默抹掉另一设备的修改），
    在 conflicts 中返回服务端最新答案，由客户端提示并加载。
    其余题目正常写入，写入后版本号递增。
    """
    if attempt.status != "in_progress":
        raise ValueError("考试已结束，答案已锁定")

    existing = {
        a.question_id: a
        for a in db.query(ExamAnswer).filter(ExamAnswer.attempt_id == attempt.id).all()
    }

    # 本卷内题目的合法集合，防止写入试卷之外的 question_id
    valid_qids = {
        eq.question_id
        for eq in db.query(ExamQuestion)
        .filter(ExamQuestion.exam_id == attempt.exam_id)
        .all()
    }

    new_version = attempt.answer_version + 1
    now = datetime.now()
    conflicts: list[dict] = []
    changed: list[ExamAnswer] = []
    pending_insert: list[AnswerSubmit] = []

    for ans in data.answers:
        if ans.question_id not in valid_qids:
            continue
        row = existing.get(ans.question_id)
        if row is not None:
            if row.version > ans.base_version:
                # 另一设备更新过：保留服务端版本，回传冲突
                conflicts.append({
                    "question_id": row.question_id,
                    "server_answer": row.user_answer,
                    "server_version": row.version,
                })
                continue
            row.user_answer = ans.user_answer
            row.time_spent_seconds = max(0, ans.time_spent_seconds)
            row.version = new_version
            row.updated_at = now
            changed.append(row)
        else:
            pending_insert.append(ans)

    inserted = 0
    if pending_insert:
        try:
            for ans in pending_insert:
                db.add(ExamAnswer(
                    attempt_id=attempt.id,
                    question_id=ans.question_id,
                    user_answer=ans.user_answer,
                    time_spent_seconds=max(0, ans.time_spent_seconds),
                    version=new_version,
                    updated_at=now,
                ))
                inserted += 1
            db.flush()
        except IntegrityError:
            # 与另一设备的并发插入撞唯一约束：回滚后改为按行 upsert 重试一次
            if _retry >= 1:
                raise
            db.rollback()
            db.refresh(attempt)
            return save_answers(db, attempt, data, _retry=_retry + 1)

    saved = len(changed) + inserted
    if saved:
        attempt.answer_version = new_version
        attempt.last_save_time = now
        db.commit()
    else:
        db.rollback()

    return {
        "answer_version": attempt.answer_version,
        "saved_count": saved,
        "conflicts": conflicts,
    }


# ---------- 交卷评分（幂等） ----------
def _grade_stored_answers(db: Session, attempt: ExamAttempt, exam: Exam) -> float:
    """基于已保存的 ExamAnswer 逐题评分，回写每题 is_correct/score，返回总分。"""
    question_map = {
        eq.question_id: eq.score
        for eq in db.query(ExamQuestion).filter(ExamQuestion.exam_id == exam.id).all()
    }
    total_score = 0.0
    for row in get_saved_answers(db, attempt):
        question = db.query(Question).filter(Question.id == row.question_id).first()
        if not question:
            continue
        full_score = float(question_map.get(question.id, 5))
        answer = AnswerSubmit(
            question_id=row.question_id,
            user_answer=row.user_answer,
            time_spent_seconds=row.time_spent_seconds,
        )
        correct, got_score = _grade_answer(question, answer, full_score)
        row.is_correct = 1 if correct else 0
        row.score = got_score
        total_score += got_score
    return round(total_score, 1)


def finalize_attempt(db: Session, attempt: ExamAttempt, submit_type: str = "manual") -> ExamAttempt:
    """把进行中的考试原子地置为 graded，仅第一次调用真正评分。

    通过条件更新（UPDATE ... WHERE status='in_progress'，写锁串行化）保证：
    重复请求（超时自动交卷与手动交卷并发、网络重试）不会重复计分、
    重复占用考试次数或重复发证。
    返回最新的 attempt（已是 graded 时调用方据此做幂等返回）。
    """
    db.refresh(attempt)
    if attempt.status != "in_progress":
        return attempt

    exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
    if not exam:
        raise ValueError("考试不存在")

    # 原子抢占：只有状态仍是 in_progress 才允许进入评分（并发下仅一个请求成功）
    claimed = db.execute(
        update(ExamAttempt)
        .where(ExamAttempt.id == attempt.id, ExamAttempt.status == "in_progress")
        .values(status="submitted")
    )
    if claimed.rowcount == 0:
        db.rollback()
        db.refresh(attempt)
        return attempt

    total_score = _grade_stored_answers(db, attempt, exam)
    now = datetime.now()
    attempt.score = total_score
    attempt.submit_time = now
    attempt.status = "graded"
    attempt.submit_type = submit_type
    attempt.is_passed = 1 if attempt.score >= exam.pass_score else 0
    db.commit()
    db.refresh(attempt)

    # 瞬态标记（不入库）：供 API 判断本次是否真正完成评分，以区分重复提交
    attempt._just_finalized = True

    # 预约/补考联动：通过考试后自动发放证书（发证自身也做去重）
    from app.services import grade_service
    grade_service.auto_issue_certificate(db, attempt)
    return attempt


def submit_exam(db: Session, attempt: ExamAttempt,
                data: ExamSubmitRequest | None = None) -> ExamAttempt:
    """交卷（兼容旧调用）。

    - 未超时：先把本次携带的答案保存，再评分；
    - 已超时：拒绝新答案，按服务端已保存的答案自动交卷（submit_type=timeout）；
    - 已交卷：幂等返回，不重复评分/发证/占用次数。
    """
    db.refresh(attempt)
    if attempt.status == "graded":
        return attempt

    exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
    if not exam:
        raise ValueError("考试不存在")

    deadline = get_deadline(attempt, exam)
    expired = datetime.now() > deadline

    if expired:
        return finalize_attempt(db, attempt, submit_type="timeout")

    if data is not None and data.answers:
        save_answers(db, attempt, AnswerSaveRequest(answers=data.answers))
        db.refresh(attempt)
    return finalize_attempt(db, attempt, submit_type=(data.submit_type if data else "manual"))


def auto_submit_if_expired(db: Session, attempt: ExamAttempt) -> bool:
    """若考试已到时则按已保存答案自动交卷。返回本次是否发生了自动交卷。"""
    db.refresh(attempt)
    if attempt.status != "in_progress":
        return False
    exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
    if not exam:
        return False
    if datetime.now() <= get_deadline(attempt, exam):
        return False
    finalize_attempt(db, attempt, submit_type="timeout")
    return True


def auto_submit_due_attempts(db: Session, limit: int = 100) -> int:
    """扫描所有到时仍在进行中的考试并自动交卷（后台定时任务调用）。"""
    due = db.query(ExamAttempt).filter(ExamAttempt.status == "in_progress").all()
    count = 0
    for attempt in due[:limit]:
        exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
        if exam and datetime.now() > get_deadline(attempt, exam):
            try:
                finalize_attempt(db, attempt, submit_type="timeout")
                count += 1
            except ValueError:
                continue
    return count


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
    return get_saved_answers(db, attempt)
