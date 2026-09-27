"""
成绩排名测试。
正确行为：排名统计只应包含"已交卷(graded)"的记录，
未完成的考试（0 分，in_progress）不应计入 total。
"""
from datetime import datetime

from app.models import Exam, ExamAttempt
from app.services import grade_service


def _make_exam(db):
    exam = Exam(title="排名测试", subject_id=1, duration_minutes=60,
                total_score=100, pass_score=60, status="published", created_by=1)
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam


def test_rank_ignores_unfinished_attempts(db, make_user):
    exam = _make_exam(db)
    high = make_user("high_student")
    mid = make_user("mid_student")
    unfinished = make_user("unfinished_student")

    # 高分组：90 分（已交卷）
    db.add(ExamAttempt(exam_id=exam.id, user_id=high.id,
                       start_time=datetime.now(), submit_time=datetime.now(),
                       score=90, status="graded", is_passed=1))
    # 中分组：80 分（已交卷）
    db.add(ExamAttempt(exam_id=exam.id, user_id=mid.id,
                       start_time=datetime.now(), submit_time=datetime.now(),
                       score=80, status="graded", is_passed=1))
    # 未完成：0 分（不应参与统计）
    db.add(ExamAttempt(exam_id=exam.id, user_id=unfinished.id,
                       start_time=datetime.now(), status="in_progress"))
    db.commit()

    result = grade_service.get_user_rank(db, mid.id, exam.id)

    # 正确行为：只有 2 个已交卷记录参与排名
    assert result["rank"] == 2
    assert result["total"] == 2, f"统计不应包含未完成的考试，实际 total={result['total']}"
    assert result["percentile"] == 50.0, f"第 2 名/共 2 人应为 50 分位，实际 {result['percentile']}"
