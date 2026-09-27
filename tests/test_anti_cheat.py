"""
防作弊切屏计数测试。
正确行为：cheat_warning_count 是"触发警告的次数"累计值，
每次切屏到达阈值都应累加，不应被切屏总数覆盖。
"""
from datetime import datetime

from app.models import Exam, ExamAttempt
from app.services import anti_cheat_service


def test_warning_count_accumulates(db, make_user):
    exam = Exam(title="防作弊测试", subject_id=1, duration_minutes=60,
                total_score=100, pass_score=60, status="published", created_by=1)
    db.add(exam)
    db.commit()

    user = make_user("cheat_student")
    attempt = ExamAttempt(exam_id=exam.id, user_id=user.id,
                          start_time=datetime.now())
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    # 切屏 2 次
    anti_cheat_service.record_screen_switch(db, attempt)
    anti_cheat_service.record_screen_switch(db, attempt)

    # 答题用时异常 1 次（也会触发一次警告）
    anti_cheat_service.validate_answer_time(db, attempt, question_id=1, time_spent_seconds=1)

    # 再切屏 1 次
    anti_cheat_service.record_screen_switch(db, attempt)

    # 切屏 2 次 + 答题异常 1 次 + 再切屏 1 次，累计触发警告应为 4 次
    assert attempt.cheat_warning_count == 4, \
        f"警告次数应累计为 4，实际 {attempt.cheat_warning_count}"


def test_force_submit_when_exceed_limit(db, make_user):
    from app.core.config import settings
    exam = Exam(title="防作弊测试2", subject_id=1, duration_minutes=60,
                total_score=100, pass_score=60, status="published", created_by=1)
    db.add(exam)
    db.commit()
    user = make_user("cheat_student2")
    attempt = ExamAttempt(exam_id=exam.id, user_id=user.id,
                          start_time=datetime.now())
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    force = False
    for _ in range(settings.MAX_SCREEN_SWITCH_COUNT):
        force = anti_cheat_service.record_screen_switch(db, attempt)
    assert force is True, "超过最大切屏次数应触发强制交卷"
