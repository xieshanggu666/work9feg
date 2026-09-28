"""
考试超时行为测试。
正确行为：
- 超过截止时刻后，主动提交不再被拒绝——服务端按「已自动保存的答案」评分；
- 迟到请求体里的答案不会被采纳（必须先经过自动保存）；
- 截止时刻内提交正常评分。
"""
from datetime import datetime, timedelta

from app.models import Exam, ExamAttempt
from app.schemas.attempt import ExamAutosaveRequest, ExamSubmitRequest
from app.services import attempt_service


def _make_exam(db, duration=60):
    exam = Exam(title="超时测试", subject_id=1, duration_minutes=duration,
                total_score=100, pass_score=60, status="published", created_by=1)
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam


def test_submit_after_deadline_grades_saved_answers(db, make_question, make_user):
    """开始 2 小时后（时长 60 分钟）交卷：按自动保存的答案评分，迟到请求体被忽略"""
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

    # 1) 自动保存接口在已超时情况下应先触发服务端自动交卷，拒绝保存
    res = attempt_service.save_answers(db, attempt, ExamAutosaveRequest(answers=[
        {"question_id": q.id, "user_answer": "1", "base_version": 0},
    ]))
    assert res["status"] == "graded"

    db.refresh(attempt)
    assert attempt.status == "graded"
    # 超时的保存请求未被采纳：无答案 -> 0 分
    assert attempt.score == 0.0


def test_submit_after_deadline_ignores_late_payload(db, make_question, make_user):
    """已自动保存的答案参与超时评分；请求体中未保存过的新答案不参与。"""
    exam = _make_exam(db, duration=60)
    user = make_user("student_t3")
    q = make_question("single_choice", correct_ids=(1,))

    attempt = ExamAttempt(exam_id=exam.id, user_id=user.id)
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    # 在时限内自动保存了一个错误答案
    attempt_service.save_answers(db, attempt, ExamAutosaveRequest(answers=[
        {"question_id": q.id, "user_answer": "2", "base_version": 0},
    ]))

    # 手动把开始时间拨到 2 小时前，模拟到时
    attempt.start_time = datetime.now() - timedelta(hours=2)
    db.commit()
    db.refresh(attempt)

    # 请求体里带着正确答案，但已超时 -> 不应采纳
    attempt = attempt_service.submit_exam(db, attempt, ExamSubmitRequest(answers=[
        {"question_id": q.id, "user_answer": "1", "time_spent_seconds": 30},
    ]))
    assert attempt.status == "graded"
    assert attempt.score == 0.0


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
