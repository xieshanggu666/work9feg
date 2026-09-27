"""
考试超时判断测试。
正确行为：超过考试时长（start_time + duration）后提交应被拒绝。
"""
from datetime import datetime, timedelta

from app.models import Exam, ExamAttempt
from app.schemas.attempt import ExamSubmitRequest
from app.services import attempt_service


def _make_exam(db, duration=60):
    exam = Exam(title="超时测试", subject_id=1, duration_minutes=duration,
                total_score=100, pass_score=60, status="published", created_by=1)
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam


def test_submit_after_deadline_rejected(db, make_question, make_user):
    """开始考试 2 小时后（时长 60 分钟）提交，应判定超时并拒绝"""
    exam = _make_exam(db, duration=60)
    user = make_user("student_t")
    q = make_question("single_choice", correct_ids=(1,))

    attempt = ExamAttempt(
        exam_id=exam.id, user_id=user.id,
        start_time=datetime.now() - timedelta(hours=2),  # 2 小时前开始
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    import pytest
    with pytest.raises(ValueError, match="超时"):
        attempt_service.submit_exam(db, attempt, ExamSubmitRequest(answers=[
            {"question_id": q.id, "user_answer": "1", "time_spent_seconds": 30},
        ]))


def test_submit_within_deadline_ok(db, make_question, make_user):
    """考试时长内提交应正常完成"""
    exam = _make_exam(db, duration=60)
    user = make_user("student_t2")
    q = make_question("single_choice", correct_ids=(1,))

    attempt = ExamAttempt(exam_id=exam.id, user_id=user.id)
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    attempt = attempt_service.submit_exam(db, attempt, ExamSubmitRequest(answers=[
        {"question_id": q.id, "user_answer": "1", "time_spent_seconds": 30},
    ]))
    assert attempt.status == "graded"
    assert attempt.score == 5.0
