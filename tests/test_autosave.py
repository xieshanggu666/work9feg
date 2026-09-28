"""
答题自动保存 / 恢复 / 多端冲突 / 到时自动交卷 / 重复提交幂等 测试。
"""
import threading
from datetime import datetime, timedelta

from app.models import Exam, ExamAttempt, ExamQuestion, Certificate
from app.schemas.attempt import ExamAutosaveRequest, ExamSubmitRequest
from app.services import attempt_service


def _make_exam_with_question(db, make_question, *, duration=60, max_attempts=1):
    exam = Exam(title="自动保存测试", subject_id=1, duration_minutes=duration,
                total_score=100, pass_score=60, status="published", created_by=1,
                require_booking=0, max_attempts=max_attempts)
    db.add(exam)
    db.commit()
    db.refresh(exam)
    q = make_question("single_choice", correct_ids=(1,))
    db.add(ExamQuestion(exam_id=exam.id, question_id=q.id, score=10, order_index=0))
    db.commit()
    return exam, q


def _make_attempt(db, exam, user, started_ago_minutes=0):
    attempt = ExamAttempt(
        exam_id=exam.id, user_id=user.id,
        start_time=datetime.now() - timedelta(minutes=started_ago_minutes),
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


# ---------- 自动保存 ----------
def test_autosave_creates_draft_and_bumps_version(db, make_question, make_user):
    exam, q = _make_exam_with_question(db, make_question)
    user = make_user("save1")
    attempt = _make_attempt(db, exam, user)

    res = attempt_service.save_answers(db, attempt, ExamAutosaveRequest(answers=[
        {"question_id": q.id, "user_answer": "1", "time_spent_seconds": 12,
         "base_version": 0},
    ]))
    assert res["status"] == "in_progress"
    assert res["versions"][str(q.id)] == 1
    drafts = attempt_service.get_draft_answers(db, attempt.id)
    assert len(drafts) == 1
    assert drafts[0].user_answer == "1"
    assert drafts[0].version == 1

    # 再次保存（基准版本正确）-> version=2
    res = attempt_service.save_answers(db, attempt, ExamAutosaveRequest(answers=[
        {"question_id": q.id, "user_answer": "2", "base_version": 1},
    ]))
    assert res["versions"][str(q.id)] == 2


def test_autosave_conflict_stale_base_version(db, make_question, make_user):
    """多端冲突：B 端基于旧版本保存应被拒绝并回传服务端版本。"""
    exam, q = _make_exam_with_question(db, make_question)
    user = make_user("save2")
    attempt = _make_attempt(db, exam, user)

    # A 端先保存到 version=2
    attempt_service.save_answers(db, attempt, ExamAutosaveRequest(answers=[
        {"question_id": q.id, "user_answer": "A1", "base_version": 0},
    ]))
    attempt_service.save_answers(db, attempt, ExamAutosaveRequest(answers=[
        {"question_id": q.id, "user_answer": "A2", "base_version": 1},
    ]))

    # B 端仍以 base_version=0 保存 -> 冲突，服务端答案不被覆盖
    res = attempt_service.save_answers(db, attempt, ExamAutosaveRequest(answers=[
        {"question_id": q.id, "user_answer": "B", "base_version": 0},
    ]))
    assert len(res["conflicts"]) == 1
    conflict = res["conflicts"][0]
    assert conflict["server_answer"] == "A2"
    assert conflict["server_version"] == 2
    assert conflict["client_answer"] == "B"
    draft = attempt_service.get_draft_answers(db, attempt.id)[0]
    assert draft.user_answer == "A2"
    assert draft.version == 2

    # B 端拉取到最新版本后再保存（base_version=2）-> 成功
    res = attempt_service.save_answers(db, attempt, ExamAutosaveRequest(answers=[
        {"question_id": q.id, "user_answer": "B2", "base_version": 2},
    ]))
    assert res["conflicts"] == []
    assert res["versions"][str(q.id)] == 3


def test_resume_returns_saved_answers(db, make_question, make_user):
    """刷新/重连后恢复答案与版本（对应 /resume 的服务层数据来源）。"""
    exam, q = _make_exam_with_question(db, make_question)
    user = make_user("save3")
    attempt = _make_attempt(db, exam, user)
    attempt_service.save_answers(db, attempt, ExamAutosaveRequest(answers=[
        {"question_id": q.id, "user_answer": "1", "base_version": 0},
    ]))
    drafts = attempt_service.get_draft_answers(db, attempt.id)
    assert drafts[0].user_answer == "1"
    assert drafts[0].version == 1
    deadline = attempt_service.get_deadline(attempt, exam)
    assert deadline == attempt.start_time + timedelta(minutes=exam.duration_minutes)


# ---------- 到时自动交卷 ----------
def test_sweeper_auto_submits_due_attempt_with_saved_answers(db, make_question, make_user):
    exam, q = _make_exam_with_question(db, make_question, duration=60)
    user = make_user("sweep1")
    attempt = _make_attempt(db, exam, user)
    attempt_service.save_answers(db, attempt, ExamAutosaveRequest(answers=[
        {"question_id": q.id, "user_answer": "1", "base_version": 0},
    ]))

    # 开考于 61 分钟前，已到时
    attempt.start_time = datetime.now() - timedelta(minutes=61)
    db.commit()

    count = attempt_service.auto_submit_due_attempts(db)
    assert count == 1
    db.refresh(attempt)
    assert attempt.status == "graded"
    assert attempt.submit_time is not None
    assert attempt.score == 10.0  # 已保存的正确答案被评分
    assert attempt.is_passed == 0  # 10/100 未及格
    # 自动发证只发给通过者：未及格不发证
    certs = db.query(Certificate).filter(
        Certificate.user_id == user.id, Certificate.exam_id == exam.id).count()
    assert certs == 0


def test_sweeper_skips_attempts_within_window(db, make_question, make_user):
    exam, q = _make_exam_with_question(db, make_question, duration=60)
    user = make_user("sweep2")
    attempt = _make_attempt(db, exam, user, started_ago_minutes=10)
    count = attempt_service.auto_submit_due_attempts(db)
    assert count == 0
    db.refresh(attempt)
    assert attempt.status == "in_progress"


def test_restart_recovers_due_attempt(db, make_question, make_user):
    """服务重启场景：停机期间到期的考试在启动首次扫描时被补交。"""
    exam, q = _make_exam_with_question(db, make_question, duration=30)
    user = make_user("sweep3")
    attempt = _make_attempt(db, exam, user)
    attempt_service.save_answers(db, attempt, ExamAutosaveRequest(answers=[
        {"question_id": q.id, "user_answer": "1", "base_version": 0},
    ]))
    attempt.start_time = datetime.now() - timedelta(hours=3)
    db.commit()

    # 首次扫描（等价于新进程启动）
    assert attempt_service.auto_submit_due_attempts(db) == 1
    # 再次扫描不重复交卷
    assert attempt_service.auto_submit_due_attempts(db) == 0


# ---------- 幂等交卷 ----------
def test_submit_idempotent_repeated_requests(db, make_question, make_user):
    """重复交卷请求只评分一次：成绩、submit_time 不变，不重复发证。"""
    exam, q = _make_exam_with_question(db, make_question)
    exam.pass_score = 10  # 使该题答对即通过，便于验证发证幂等
    db.commit()
    user = make_user("idem1")
    attempt = _make_attempt(db, exam, user)
    payload = ExamSubmitRequest(answers=[
        {"question_id": q.id, "user_answer": "1", "time_spent_seconds": 30},
    ])

    a1 = attempt_service.grade_attempt(db, attempt, data=payload)
    first_submit_time = a1.submit_time
    first_score = a1.score
    assert a1.status == "graded"

    # 模拟第二次（迟到/重复）请求，携带不同答案
    a2 = attempt_service.grade_attempt(db, attempt, data=ExamSubmitRequest(answers=[
        {"question_id": q.id, "user_answer": "2", "time_spent_seconds": 99},
    ]))
    assert a2.score == first_score == 10.0
    assert a2.submit_time == first_submit_time

    cert_count = db.query(Certificate).filter(
        Certificate.user_id == user.id, Certificate.exam_id == exam.id).count()
    assert cert_count == 1


def test_concurrent_submit_grades_once(db, make_question, make_user):
    """多端/前端重试并发交卷：只评分一次。"""
    exam, q = _make_exam_with_question(db, make_question)
    user = make_user("idem2")
    attempt = _make_attempt(db, exam, user)

    results = []
    errors = []

    def worker(answer):
        try:
            # 每个线程使用独立 session（与真实多请求一致），共用同一 engine
            from sqlalchemy.orm import sessionmaker
            tdb = sessionmaker(bind=db.get_bind())()
            lock = attempt_service.get_attempt_lock(attempt.id)
            # 先在锁外拿引用会与 StaticPool 的单连接竞争，这里取锁后再查
            with lock:
                tattempt = tdb.query(ExamAttempt).get(attempt.id)
                # RLock 可重入：grade_attempt 内部会再次取锁并复查状态
                graded = attempt_service.grade_attempt(tdb, tattempt, data=ExamSubmitRequest(
                    answers=[{"question_id": q.id, "user_answer": answer,
                              "time_spent_seconds": 30}]))
                results.append(graded.score)
            tdb.close()
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(ans,)) for ans in ("1", "2", "1")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(results) == 3
    # 三次请求得到同一个分数，且答案行只有一条
    assert len(set(results)) == 1
    from app.models import ExamAnswer
    # 注意：线程内使用的是内存共享 engine（conftest StaticPool）
    rows = db.query(ExamAnswer).filter(ExamAnswer.attempt_id == attempt.id).all()
    assert len(rows) == 1


def test_start_exam_does_not_reconsume_after_graded(db, make_question, make_user):
    """已交卷后刷新/重连：复用原记录，不新建 attempt（不重复占用考试次数）。"""
    import pytest
    exam, q = _make_exam_with_question(db, make_question, max_attempts=1)
    user = make_user("idem3")
    attempt = _make_attempt(db, exam, user)
    attempt_service.grade_attempt(db, attempt, data=ExamSubmitRequest(answers=[]))

    # 显式开考（不带 resume）仍按次数规则拒绝
    with pytest.raises(ValueError, match="次数"):
        attempt_service.start_exam(db, exam, user.id, ip="127.0.0.1", user_agent="pytest")

    # 刷新/重连（resume=True）：返回已交卷原记录，不产生新 attempt
    again = attempt_service.start_exam(
        db, exam, user.id, ip="127.0.0.1", user_agent="pytest", resume=True)
    assert again.id == attempt.id
    assert again.status == "graded"
    total = db.query(ExamAttempt).filter(
        ExamAttempt.exam_id == exam.id, ExamAttempt.user_id == user.id).count()
    assert total == 1


# ---------- 保存 + 到时评分的衔接 ----------
def test_graded_attempt_rejects_further_saves(db, make_question, make_user):
    exam, q = _make_exam_with_question(db, make_question)
    user = make_user("save4")
    attempt = _make_attempt(db, exam, user)
    attempt_service.save_answers(db, attempt, ExamAutosaveRequest(answers=[
        {"question_id": q.id, "user_answer": "1", "base_version": 0},
    ]))
    attempt_service.grade_attempt(db, attempt, data=ExamSubmitRequest(answers=[]))

    res = attempt_service.save_answers(db, attempt, ExamAutosaveRequest(answers=[
        {"question_id": q.id, "user_answer": "9", "base_version": 1},
    ]))
    assert res["status"] == "graded"
    draft = attempt_service.get_draft_answers(db, attempt.id)[0]
    assert draft.user_answer == "1"  # 交卷后的保存不生效
