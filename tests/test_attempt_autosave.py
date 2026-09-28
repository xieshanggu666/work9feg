"""
答题自动保存 / 刷新恢复 / 多端冲突 / 到时自动交卷 / 交卷幂等 测试。
"""
from datetime import datetime, timedelta

from app.models import Exam, ExamAttempt, ExamQuestion, Certificate
from app.schemas.attempt import AnswerSaveRequest, ExamSubmitRequest
from app.services import attempt_service


def _make_exam_with_question(db, make_question, duration=60, pass_score=60):
    exam = Exam(title="保存测试", subject_id=1, duration_minutes=duration,
                total_score=5, pass_score=pass_score, status="published", created_by=1)
    db.add(exam)
    db.commit()
    db.refresh(exam)
    q = make_question("single_choice", correct_ids=(1,))
    db.add(ExamQuestion(exam_id=exam.id, question_id=q.id, score=5, order_index=0))
    db.commit()
    return exam, q


def _start(db, exam, user):
    attempt = ExamAttempt(exam_id=exam.id, user_id=user.id)
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


def test_autosave_then_resume(db, make_user, make_question):
    """自动保存后可从服务端读回草稿（刷新/重连恢复答案与版本）"""
    exam, q = _make_exam_with_question(db, make_question)
    user = make_user("sv_student")
    attempt = _start(db, exam, user)

    res = attempt_service.save_answers(db, attempt, AnswerSaveRequest(answers=[
        {"question_id": q.id, "user_answer": "1", "time_spent_seconds": 12},
    ]))
    assert res["saved_count"] == 1
    assert res["answer_version"] == 1
    assert res["conflicts"] == []

    saved = attempt_service.get_saved_answers(db, attempt)
    assert len(saved) == 1
    assert saved[0].user_answer == "1"
    assert saved[0].version == 1


def test_save_after_submit_locked(db, make_user, make_question):
    """交卷后答案锁定，不能再保存"""
    import pytest
    exam, q = _make_exam_with_question(db, make_question)
    user = make_user("sv_student2")
    attempt = _start(db, exam, user)
    attempt_service.submit_exam(db, attempt, ExamSubmitRequest(answers=[
        {"question_id": q.id, "user_answer": "1", "time_spent_seconds": 10},
    ]))
    with pytest.raises(ValueError, match="锁定"):
        attempt_service.save_answers(db, attempt, AnswerSaveRequest(answers=[
            {"question_id": q.id, "user_answer": "2", "time_spent_seconds": 10},
        ]))


def test_multi_device_conflict_server_wins(db, make_user, make_question):
    """设备 B 已更新后，设备 A 用旧 base_version 保存不应覆盖，返回冲突"""
    exam, q = _make_exam_with_question(db, make_question)
    user = make_user("sv_student3")
    attempt = _start(db, exam, user)

    # 设备 A 保存 "1" -> version 1
    attempt_service.save_answers(db, attempt, AnswerSaveRequest(answers=[
        {"question_id": q.id, "user_answer": "1", "time_spent_seconds": 5,
         "base_version": 0},
    ]))
    # 设备 B 同步到 v1 后改成 "2" -> version 2
    attempt_service.save_answers(db, attempt, AnswerSaveRequest(answers=[
        {"question_id": q.id, "user_answer": "2", "time_spent_seconds": 6,
         "base_version": 1},
    ]))
    # 设备 A 仍基于 v1 想写回 "1" -> 冲突，服务端保留 "2"
    res = attempt_service.save_answers(db, attempt, AnswerSaveRequest(answers=[
        {"question_id": q.id, "user_answer": "1", "time_spent_seconds": 7,
         "base_version": 1},
    ]))
    assert len(res["conflicts"]) == 1
    assert res["conflicts"][0]["server_answer"] == "2"
    saved = {a.question_id: a for a in attempt_service.get_saved_answers(db, attempt)}
    assert saved[q.id].user_answer == "2"


def test_submit_idempotent_no_double_grade_or_cert(db, make_user, make_question):
    """重复交卷：只评分一次、只发一张证"""
    exam, q = _make_exam_with_question(db, make_question, pass_score=5)
    user = make_user("sv_student4")
    attempt = _start(db, exam, user)

    req = ExamSubmitRequest(answers=[
        {"question_id": q.id, "user_answer": "1", "time_spent_seconds": 10},
    ])
    first = attempt_service.submit_exam(db, attempt, req)
    assert first.status == "graded"
    assert first.score == 5.0

    # 网络重试 / 多端重复点击，再交一次
    second = attempt_service.submit_exam(db, attempt, ExamSubmitRequest(answers=[
        {"question_id": q.id, "user_answer": "2", "time_spent_seconds": 10},
    ]))
    assert second.id == first.id
    assert second.score == 5.0  # 分数未被第二次错误答案改变

    answers = attempt_service.get_saved_answers(db, attempt)
    assert len(answers) == 1
    certs = db.query(Certificate).filter(
        Certificate.user_id == user.id, Certificate.exam_id == exam.id
    ).count()
    assert certs == 1


def test_attempt_count_consumed_once(db, make_user, make_question):
    """重复交卷/自动交卷不会重复占用考试次数（仅产生一次 graded 记录）"""
    exam, q = _make_exam_with_question(db, make_question, pass_score=5)
    user = make_user("sv_student5")
    attempt = _start(db, exam, user)

    attempt_service.submit_exam(db, attempt, ExamSubmitRequest(answers=[
        {"question_id": q.id, "user_answer": "1", "time_spent_seconds": 10},
    ]))
    # 模拟到时扫描对同一记录再处理
    attempt_service.auto_submit_if_expired(db, attempt)
    attempt_service.finalize_attempt(db, attempt, submit_type="timeout")

    graded = db.query(ExamAttempt).filter(
        ExamAttempt.exam_id == exam.id,
        ExamAttempt.user_id == user.id,
        ExamAttempt.status == "graded",
    ).count()
    assert graded == 1


def test_saved_draft_used_when_no_submit_payload(db, make_user, make_question):
    """到时自动交卷时，即使没带答案，也按已保存草稿评分"""
    exam, q = _make_exam_with_question(db, make_question, pass_score=5)
    user = make_user("sv_student6")
    attempt = ExamAttempt(
        exam_id=exam.id, user_id=user.id,
        start_time=datetime.now() - timedelta(minutes=61),
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    attempt_service.save_answers(db, attempt, AnswerSaveRequest(answers=[
        {"question_id": q.id, "user_answer": "1", "time_spent_seconds": 15},
    ]))
    attempt_service.auto_submit_due_attempts(db)
    db.refresh(attempt)
    assert attempt.status == "graded"
    assert attempt.submit_type == "timeout"
    assert attempt.score == 5.0


def test_invalid_question_not_saved(db, make_user, make_question):
    """试卷之外的 question_id 不允许写入草稿"""
    exam, q = _make_exam_with_question(db, make_question)
    other = make_question("single_choice", correct_ids=(1,))
    user = make_user("sv_student7")
    attempt = _start(db, exam, user)

    res = attempt_service.save_answers(db, attempt, AnswerSaveRequest(answers=[
        {"question_id": other.id, "user_answer": "1", "time_spent_seconds": 5},
    ]))
    assert res["saved_count"] == 0
    assert attempt_service.get_saved_answers(db, attempt) == []
