import threading
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Exam, ExamAttempt, ExamAnswer, ExamQuestion, Question,
)
from app.schemas.attempt import (
    AnswerSubmit, ExamAutosaveRequest, ExamSubmitRequest,
)
from app.services import booking_service

# 每次考试一把进程内锁：串行化同一次考试的「自动保存 / 交卷 / 到时自动交卷」，
# 保证重复与并发请求只评分、只占用次数、只发证一次。
_attempt_locks: dict[int, threading.RLock] = {}
# 开考按「用户 + 考试」串行化，避免并发首考双双通过资格检查造成重复占次数。
_start_locks: dict[tuple[int, int], threading.RLock] = {}
_locks_guard = threading.Lock()


def get_attempt_lock(attempt_id: int) -> threading.RLock:
    with _locks_guard:
        lock = _attempt_locks.get(attempt_id)
        if lock is None:
            lock = threading.RLock()
            _attempt_locks[attempt_id] = lock
        return lock


def _get_start_lock(exam_id: int, user_id: int) -> threading.RLock:
    key = (exam_id, user_id)
    with _locks_guard:
        lock = _start_locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _start_locks[key] = lock
        return lock


def get_deadline(attempt: ExamAttempt, exam: Exam) -> datetime:
    """考试截止时刻 = 开考时间 + 时长（权威，剩余时间始终由它推导）。"""
    return attempt.start_time + timedelta(minutes=exam.duration_minutes)


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


def start_exam(db: Session, exam: Exam, user_id: int, ip: str, user_agent: str,
               resume: bool = False) -> ExamAttempt:
    """开始考试。

    开考资格与次数由预约模块驱动：
    - 进行中的考试直接返回原记录（刷新 / 重连 / 多端进入都复用同一条）；
    - 最近一次已交卷（graded）但仍有开考资格（如补考预约已通过）时，正常新建考试；
    - resume=True（前端进入考试页，可能是刷新/重连）时，已交卷且不具备新开考
      资格（已通过 / 次数用尽 / 无预约）返回原记录，不重复占用考试次数，
      由接口层告知前端该场已结束；resume=False 时按资格规则抛错；
    - 无需预约的考试受 max_attempts 限制；
    - 需预约的考试必须存在已通过、在时段窗口内且场次匹配的预约，
      开考成功后预约标记为 used。
    """
    with _get_start_lock(exam.id, user_id):
        in_progress = (
            db.query(ExamAttempt)
            .filter(
                ExamAttempt.exam_id == exam.id,
                ExamAttempt.user_id == user_id,
                ExamAttempt.status == "in_progress",
            )
            .first()
        )
        if in_progress:
            return in_progress

        latest = (
            db.query(ExamAttempt)
            .filter(ExamAttempt.exam_id == exam.id, ExamAttempt.user_id == user_id)
            .order_by(ExamAttempt.id.desc())
            .first()
        )

        eligibility = booking_service.check_eligibility(db, exam, user_id)
        if not eligibility["can_start"]:
            # 刷新/重连场景：已交过卷则返回原记录（接口层据此恢复到结果页），
            # 而不是再消耗一次机会；其它调用方仍收到明确的资格错误
            if resume and latest and latest.status in ("submitted", "graded"):
                return latest
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


# ---------- 自动保存 ----------
def get_draft_answers(db: Session, attempt_id: int) -> list[ExamAnswer]:
    """读取已自动保存的草稿答案（刷新 / 重连恢复用）。"""
    return (
        db.query(ExamAnswer)
        .filter(ExamAnswer.attempt_id == attempt_id)
        .order_by(ExamAnswer.question_id.asc())
        .all()
    )


def save_answers(db: Session, attempt: ExamAttempt,
                 data: ExamAutosaveRequest) -> dict:
    """逐题自动保存（草稿 upsert），返回保存结果与多端冲突明细。

    冲突规则（字段级乐观锁）：客户端带 base_version；
    服务端记录版本高于基准版本，说明其它端已改过此题 → 拒绝本次覆盖并回传冲突，
    由用户决定采用哪一端；否则正常保存并 version+1。
    已交卷 / 已超时的考试不再接受保存（超时的会先由服务端自动交卷）。
    """
    exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
    if not exam:
        raise ValueError("考试不存在")

    with get_attempt_lock(attempt.id):
        db.refresh(attempt)
        if attempt.status == "graded":
            return _save_result(db, attempt, exam, [], [])

        deadline = get_deadline(attempt, exam)
        now = datetime.now()
        if now >= deadline:
            # 到时：以已保存答案自动交卷，再拒绝本次保存
            grade_attempt(db, attempt, late=True)
            return _save_result(db, attempt, exam, [], [])

        valid_qids = {eq.question_id for eq in exam.questions}
        saved: list[ExamAnswer] = []
        conflicts: list[dict] = []

        existing = {
            a.question_id: a
            for a in db.query(ExamAnswer).filter(ExamAnswer.attempt_id == attempt.id).all()
        }
        for item in data.answers:
            if item.question_id not in valid_qids:
                continue
            row = existing.get(item.question_id)
            if row is not None and row.version > item.base_version:
                # 其它端已更新：冲突，不覆盖
                conflicts.append({
                    "question_id": item.question_id,
                    "server_answer": row.user_answer,
                    "server_version": row.version,
                    "client_answer": item.user_answer,
                })
                continue

            if row is None:
                row = ExamAnswer(
                    attempt_id=attempt.id,
                    question_id=item.question_id,
                    version=0,
                )
                db.add(row)
                existing[item.question_id] = row
            row.user_answer = item.user_answer
            if item.time_spent_seconds is not None:
                # 用时只增不减，避免各端累计值互相覆盖变小
                row.time_spent_seconds = max(
                    row.time_spent_seconds or 0, item.time_spent_seconds
                )
            row.version += 1
            saved.append(row)

        db.commit()
        for row in saved:
            db.refresh(row)
        return _save_result(db, attempt, exam, saved, conflicts)


def _save_result(db: Session, attempt: ExamAttempt, exam: Exam,
                 saved: list[ExamAnswer], conflicts: list[dict]) -> dict:
    return {
        "attempt_id": attempt.id,
        "status": attempt.status,
        "server_time": datetime.now(),
        "deadline": get_deadline(attempt, exam),
        "saved": [
            {
                "question_id": row.question_id,
                "user_answer": row.user_answer,
                "time_spent_seconds": row.time_spent_seconds or 0,
                "version": row.version,
            }
            for row in saved
        ],
        "versions": {str(row.question_id): row.version for row in saved},
        "conflicts": conflicts,
    }


# ---------- 交卷 / 评分（幂等） ----------
def grade_attempt(db: Session, attempt: ExamAttempt,
                  data: ExamSubmitRequest | None = None,
                  late: bool = False) -> ExamAttempt:
    """对一次考试评分并落库。幂等：已 graded 的直接返回，绝不重复评分/发证/占用次数。

    - late=False（考生主动交卷）：截止前把本次上送的答案并入草稿后评分；
      截止后只按服务端已保存的答案评分，忽略迟到的请求体。
    - late=True（服务端到时自动交卷）：完全按已保存答案评分。
    """
    with get_attempt_lock(attempt.id):
        db.refresh(attempt)
        if attempt.status == "graded":
            return attempt  # 重复请求：直接返回已评分记录，不再做任何副作用

        exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
        if not exam:
            raise ValueError("考试不存在")
        deadline = get_deadline(attempt, exam)
        now = datetime.now()
        if not late and now < deadline and data is not None:
            _merge_submitted_answers(db, attempt, exam, data.answers)
            db.flush()

        # 答题用时异常检测（未作答或用时过短记警告；不影响交卷）
        rows = (
            db.query(ExamAnswer)
            .filter(ExamAnswer.attempt_id == attempt.id)
            .all()
        )
        warning_delta = 0
        for row in rows:
            spent = row.time_spent_seconds or 0
            # 已作答但单题用时过短记嫌疑；未作答不计速度异常
            if (row.user_answer or "") and 0 < spent < settings.MIN_ANSWER_SECONDS:
                warning_delta += 1
        full_qids = {eq.question_id for eq in exam.questions}
        # 未作答的题目同样按零分入库（见下方循环）
        if warning_delta:
            attempt.cheat_warning_count = (attempt.cheat_warning_count or 0) + warning_delta

        score_map = {eq.question_id: eq.score for eq in exam.questions}
        rows_by_qid = {row.question_id: row for row in rows}
        total_score = 0.0
        for qid in full_qids:
            row = rows_by_qid.get(qid)
            if row is None:
                row = ExamAnswer(
                    attempt_id=attempt.id, question_id=qid,
                    user_answer="", version=0,
                )
                db.add(row)
            question = db.query(Question).filter(Question.id == qid).first()
            if question is None:
                continue
            full_score = float(score_map.get(qid, 5))
            ans = AnswerSubmit(
                question_id=qid,
                user_answer=row.user_answer or "",
                time_spent_seconds=row.time_spent_seconds or 0,
            )
            correct, got_score = _grade_answer(question, ans, full_score)
            row.is_correct = 1 if correct else 0
            row.score = got_score
            total_score += got_score

        attempt.score = round(total_score, 1)
        attempt.submit_time = datetime.now()
        attempt.status = "graded"
        attempt.is_passed = 1 if attempt.score >= exam.pass_score else 0
        db.commit()
        db.refresh(attempt)

        # 发证同样幂等（已持有效证书不会重复发放，仅更新更高分）
        from app.services import grade_service
        grade_service.auto_issue_certificate(db, attempt)
        return attempt


def _merge_submitted_answers(db: Session, attempt: ExamAttempt, exam: Exam,
                             answers: list[AnswerSubmit]) -> None:
    """主动交卷时把请求体中的答案并入草稿（与自动保存合并口径一致）。"""
    valid_qids = {eq.question_id for eq in exam.questions}
    existing = {
        a.question_id: a
        for a in db.query(ExamAnswer).filter(ExamAnswer.attempt_id == attempt.id).all()
    }
    for ans in answers:
        if ans.question_id not in valid_qids:
            continue
        row = existing.get(ans.question_id)
        if row is None:
            row = ExamAnswer(
                attempt_id=attempt.id,
                question_id=ans.question_id,
                version=0,
            )
            db.add(row)
            existing[ans.question_id] = row
        row.user_answer = ans.user_answer
        if ans.time_spent_seconds:
            row.time_spent_seconds = max(
                row.time_spent_seconds or 0, ans.time_spent_seconds
            )
        row.version += 1


def submit_exam(db: Session, attempt: ExamAttempt, data: ExamSubmitRequest) -> ExamAttempt:
    """兼容旧调用入口：主动交卷。

    注意：超时不再拒绝——到时按服务端已保存答案交卷（late 路径在 grade_attempt
    内部判定），保证刷新 / 断网 / 客户端时钟错误都不会丢成绩。
    """
    return grade_attempt(db, attempt, data=data, late=False)


def auto_submit_due_attempts(db: Session, limit: int = 100) -> int:
    """扫描所有已到截止时刻仍未交卷的考试，按已保存答案自动交卷。

    服务端在启动时及之后定时调用；重启后也能恢复，不依赖前端在线。
    返回本次自动交卷的记录数。
    """
    now = datetime.now()
    due = (
        db.query(ExamAttempt)
        .filter(ExamAttempt.status == "in_progress")
        .all()
    )
    count = 0
    for attempt in due:
        exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
        if not exam:
            continue
        if now < get_deadline(attempt, exam):
            continue
        # grade_attempt 内部加锁且幂等；与前端/其它 worker 的并发交卷安全
        grade_attempt(db, attempt, late=True)
        count += 1
        if count >= limit:
            break
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
    answers = db.query(ExamAnswer).filter(ExamAnswer.attempt_id == attempt.id).all()
    return answers
