"""
考试到时行为测试。
正确行为：
- 到点前交卷：正常评分；
- 到点后：服务端按已保存答案自动交卷（submit_type=timeout），不再接收新答案；
- 重复提交幂等：不重复计分。
"""
from datetime import datetime, timedelta

from app.models import Exam, ExamAttempt
from app.schemas.attempt import AnswerSaveRequest, ExamSubmitRequest
from app.services import attempt_service


def _make_exam(db, duration=60):
    exam = Exam(title="超时测试", subject_id=1, duration_minutes=duration,
                total_score=100, pass_score=60, status="published", created_by=1)
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam


def test_submit_after_deadline_auto_submits_saved(db, make_question, make_user):
    """开考 2 小时后（时长 60 分钟）提交：按已保存答案自动交卷，忽略本次携带答案"""
    exam = _make_exam(db, duration=60)
    user = make_user("student_t")
    q = make_question("single_choice", correct_ids=(1,))

    attempt = ExamAttempt(
        exam_id=exam.id, user_id=user.id,
        start_time=datetime.now() - timedelta(hours=2),
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    # 已保存的正确答案（自动保存）
    attempt_service.save_answers(db, attempt, AnswerSaveRequest(answers=[
        {"question_id": q.id, "user_answer": "1", "time_spent_seconds": 30},
    ]))

    # 超时后携带一个错误答案提交，应被忽略并按已保存答案评分
    attempt = attempt_service.submit_exam(db, attempt, ExamSubmitRequest(answers=[
        {"question_id": q.id, "user_answer": "2", "time_spent_seconds": 30},
    ]))
    assert attempt.status == "graded"
    assert attempt.submit_type == "timeout"
    assert attempt.score == 5.0  # 按已保存的 "1" 给分


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


def test_auto_submit_if_expired_grades_saved(db, make_question, make_user):
    """到时后台扫描：无任何提交也按已保存草稿自动交卷"""
    exam = _make_exam(db, duration=60)
    user = make_user("student_t3")
    q = make_question("single_choice", correct_ids=(1,))

    attempt = ExamAttempt(
        exam_id=exam.id, user_id=user.id,
        start_time=datetime.now() - timedelta(minutes=61),
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    attempt_service.save_answers(db, attempt, AnswerSaveRequest(answers=[
        {"question_id": q.id, "user_answer": "1", "time_spent_seconds": 20},
    ]))

    fired = attempt_service.auto_submit_if_expired(db, attempt)
    assert fired is True
    assert attempt.status == "graded"
    assert attempt.submit_type == "timeout"
    assert attempt.score == 5.0

    # 再次扫描不重复交卷
    assert attempt_service.auto_submit_if_expired(db, attempt) is False
