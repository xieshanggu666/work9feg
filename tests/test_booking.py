"""
考试预约与补考管理测试。
覆盖：学生申请 → 教师审核（占名额）→ 预约状态驱动开考资格 →
次数限制 → 补考 → 成绩统计 → 证书发放。
"""
from datetime import datetime, timedelta

import pytest

from app.models import Exam, ExamAttempt, Certificate
from app.schemas.attempt import ExamSubmitRequest
from app.schemas.booking import SlotCreate
from app.services import booking_service, attempt_service, grade_service


def _make_exam(db, require_booking=1, max_attempts=2, pass_score=60):
    exam = Exam(
        title="预约测试", subject_id=1, duration_minutes=60,
        total_score=100, pass_score=pass_score, status="published", created_by=1,
        require_booking=require_booking, max_attempts=max_attempts,
    )
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam


def _make_slot(db, exam, capacity=2, start_offset_days=-1, end_offset_days=6):
    now = datetime.now()
    return booking_service.create_slot(db, exam.id, SlotCreate(
        name="测试批次",
        start_time=now + timedelta(days=start_offset_days),
        end_time=now + timedelta(days=end_offset_days),
        capacity=capacity,
    ))


def test_require_booking_blocks_start_without_booking(db, make_user):
    """必须预约的考试，未预约不能开考"""
    exam = _make_exam(db)
    student = make_user("bk_student")

    info = booking_service.check_eligibility(db, exam, student.id)
    assert info["can_start"] is False
    assert "预约" in info["reason"]

    with pytest.raises(ValueError, match="预约"):
        attempt_service.start_exam(db, exam, student.id, "", "")


def test_no_booking_required_respects_max_attempts(db, make_user, make_question):
    """无需预约的考试也受 max_attempts 限制"""
    exam = _make_exam(db, require_booking=0, max_attempts=2)
    student = make_user("free_student")
    q = make_question("single_choice", correct_ids=(1,))

    for _ in range(2):
        attempt = attempt_service.start_exam(db, exam, student.id, "", "")
        attempt_service.submit_exam(db, attempt, ExamSubmitRequest(answers=[
            {"question_id": q.id, "user_answer": "1", "time_spent_seconds": 10},
        ]))

    with pytest.raises(ValueError, match="次数"):
        attempt_service.start_exam(db, exam, student.id, "", "")


def test_apply_review_then_start(db, make_user):
    """学生申请 → 教师审核通过 → 在时段窗口内可开考，预约变为 used"""
    exam = _make_exam(db)
    teacher = make_user("bk_teacher", role="teacher")
    student = make_user("bk_student2")
    slot = _make_slot(db, exam, capacity=1)

    booking = booking_service.apply_booking(db, exam.id, slot.id, student.id)
    assert booking.status == "pending"
    assert booking.attempt_no == 1
    assert booking.booking_type == "first"
    # 待审核不占名额
    assert slot.booked_count == 0

    # 审核通过后占用名额
    booking = booking_service.review_booking(db, booking, teacher.id, True)
    assert booking.status == "approved"
    db.refresh(slot)
    assert slot.booked_count == 1

    info = booking_service.check_eligibility(db, exam, student.id)
    assert info["can_start"] is True

    attempt = attempt_service.start_exam(db, exam, student.id, "", "")
    db.refresh(booking)
    assert booking.status == "used"
    assert attempt.booking_id == booking.id
    assert attempt.attempt_no == 1


def test_rejected_booking_cannot_start(db, make_user):
    """审核驳回的预约不能开考"""
    exam = _make_exam(db)
    teacher = make_user("bk_teacher2", role="teacher")
    student = make_user("bk_student3")
    slot = _make_slot(db, exam)

    booking = booking_service.apply_booking(db, exam.id, slot.id, student.id)
    booking_service.review_booking(db, booking, teacher.id, False, "资格不符")

    info = booking_service.check_eligibility(db, exam, student.id)
    assert info["can_start"] is False
    with pytest.raises(ValueError):
        attempt_service.start_exam(db, exam, student.id, "", "")


def test_slot_capacity_enforced(db, make_user):
    """名额满后审核通过应失败"""
    exam = _make_exam(db)
    teacher = make_user("bk_teacher3", role="teacher")
    slot = _make_slot(db, exam, capacity=1)

    s1 = make_user("cap_s1")
    s2 = make_user("cap_s2")
    b1 = booking_service.apply_booking(db, exam.id, slot.id, s1.id)
    b2 = booking_service.apply_booking(db, exam.id, slot.id, s2.id)
    booking_service.review_booking(db, b1, teacher.id, True)
    db.refresh(slot)
    assert slot.booked_count == 1

    with pytest.raises(ValueError, match="名额"):
        booking_service.review_booking(db, b2, teacher.id, True)


def test_duplicate_active_booking_rejected(db, make_user):
    """同一考试已有待审核/已通过预约时不能重复申请"""
    exam = _make_exam(db)
    student = make_user("dup_student")
    slot = _make_slot(db, exam)

    booking_service.apply_booking(db, exam.id, slot.id, student.id)
    with pytest.raises(ValueError, match="重复申请"):
        booking_service.apply_booking(db, exam.id, slot.id, student.id)


def test_cancel_approved_releases_capacity(db, make_user):
    """取消已通过的预约应退回名额，并可重新申请"""
    exam = _make_exam(db)
    teacher = make_user("bk_teacher4", role="teacher")
    student = make_user("cancel_student")
    slot = _make_slot(db, exam, capacity=1)

    b = booking_service.apply_booking(db, exam.id, slot.id, student.id)
    booking_service.review_booking(db, b, teacher.id, True)
    db.refresh(slot)
    assert slot.booked_count == 1

    booking_service.cancel_booking(db, b)
    db.refresh(slot)
    assert slot.booked_count == 0

    b2 = booking_service.apply_booking(db, exam.id, slot.id, student.id)
    assert b2.status == "pending"


def test_before_slot_window_cannot_start(db, make_user):
    """未到预约开考时间不能开考"""
    exam = _make_exam(db)
    teacher = make_user("bk_teacher5", role="teacher")
    student = make_user("early_student")
    slot = _make_slot(db, exam, start_offset_days=2, end_offset_days=8)

    b = booking_service.apply_booking(db, exam.id, slot.id, student.id)
    booking_service.review_booking(db, b, teacher.id, True)

    info = booking_service.check_eligibility(db, exam, student.id)
    assert info["can_start"] is False
    assert "开考时间" in info["reason"]


def test_missed_booking_counts_as_attempt(db, make_user):
    """时段结束仍未开考 → 缺考，消耗一次考试机会"""
    exam = _make_exam(db, max_attempts=2)
    teacher = make_user("bk_teacher6", role="teacher")
    student = make_user("miss_student")

    # 直接构造一个已审核通过但时段已结束的预约（过去时段无法再申请）
    from app.models import ExamBooking
    past_slot = booking_service.create_slot(db, exam.id, SlotCreate(
        name="过去批次",
        start_time=datetime.now() - timedelta(days=3),
        end_time=datetime.now() - timedelta(days=1),
        capacity=5,
    ))
    b = ExamBooking(
        exam_id=exam.id, slot_id=past_slot.id, user_id=student.id,
        attempt_no=1, booking_type="first", status="approved",
    )
    db.add(b)
    past_slot.booked_count = 1
    db.commit()

    # 触发缺考同步
    booking_service.sync_missed(db, exam_id=exam.id, user_id=student.id)
    db.refresh(b)
    assert b.status == "missed"

    counts = booking_service._counts(db, exam.id, student.id)
    assert counts["used"] == 1


def test_retake_flow_after_failure(db, make_user, make_question):
    """首考未通过 → 可申请补考（attempt_no=2）→ 补考通过自动发证"""
    exam = _make_exam(db, max_attempts=2, pass_score=5)
    teacher = make_user("retake_teacher", role="teacher")
    student = make_user("retake_student")

    # ---- 首考：答错（0 分），未通过 ----
    slot1 = _make_slot(db, exam, capacity=5)
    b1 = booking_service.apply_booking(db, exam.id, slot1.id, student.id)
    booking_service.review_booking(db, b1, teacher.id, True)
    q_wrong = make_question("single_choice", correct_ids=(1,))
    a1 = attempt_service.start_exam(db, exam, student.id, "", "")
    attempt_service.submit_exam(db, a1, ExamSubmitRequest(answers=[
        {"question_id": q_wrong.id, "user_answer": "2", "time_spent_seconds": 10},
    ]))
    db.refresh(b1)
    assert b1.status == "used"
    assert a1.is_passed == 0
    assert a1.attempt_no == 1

    # ---- 申请补考 ----
    slot2 = _make_slot(db, exam, capacity=5)
    b2 = booking_service.apply_booking(db, exam.id, slot2.id, student.id, reason="申请补考")
    assert b2.booking_type == "retake"
    assert b2.attempt_no == 2
    booking_service.review_booking(db, b2, teacher.id, True)

    q_right = make_question("single_choice", difficulty=4, correct_ids=(3,))
    right_opt = next(o.id for o in q_right.options if o.is_correct == 1)
    a2 = attempt_service.start_exam(db, exam, student.id, "", "")
    assert a2.attempt_no == 2
    attempt_service.submit_exam(db, a2, ExamSubmitRequest(answers=[
        {"question_id": q_right.id, "user_answer": str(right_opt), "time_spent_seconds": 10},
    ]))
    assert a2.is_passed == 1

    # 补考通过自动发证
    cert = db.query(Certificate).filter(
        Certificate.user_id == student.id, Certificate.exam_id == exam.id
    ).first()
    assert cert is not None
    assert cert.score == a2.score

    # 已通过不能再次预约
    with pytest.raises(ValueError, match="已通过"):
        booking_service.apply_booking(db, exam.id, slot2.id, student.id)


def test_passed_student_blocked_from_retake_when_max_one(db, make_user, make_question):
    """max_attempts=1 且通过后不能再考"""
    exam = _make_exam(db, max_attempts=1, pass_score=5)
    teacher = make_user("once_teacher", role="teacher")
    student = make_user("once_student")
    slot = _make_slot(db, exam)

    b = booking_service.apply_booking(db, exam.id, slot.id, student.id)
    booking_service.review_booking(db, b, teacher.id, True)
    q = make_question("single_choice", correct_ids=(1,))
    a = attempt_service.start_exam(db, exam, student.id, "", "")
    attempt_service.submit_exam(db, a, ExamSubmitRequest(answers=[
        {"question_id": q.id, "user_answer": "1", "time_spent_seconds": 10},
    ]))
    assert a.is_passed == 1

    info = booking_service.check_eligibility(db, exam, student.id)
    assert info["can_start"] is False
    assert info["has_passed"] is True


def test_stats_include_booking_and_retake_metrics(db, make_user, make_question):
    """成绩统计含预约、缺考、补考维度"""
    exam = _make_exam(db, max_attempts=2, pass_score=5)
    teacher = make_user("stat_teacher", role="teacher")

    # 学生 A：首考通过
    sa = make_user("stat_a")
    slot = _make_slot(db, exam, capacity=10)
    ba = booking_service.apply_booking(db, exam.id, slot.id, sa.id)
    booking_service.review_booking(db, ba, teacher.id, True)
    q = make_question("single_choice", correct_ids=(1,))
    aa = attempt_service.start_exam(db, exam, sa.id, "", "")
    attempt_service.submit_exam(db, aa, ExamSubmitRequest(answers=[
        {"question_id": q.id, "user_answer": "1", "time_spent_seconds": 10},
    ]))

    # 学生 B：缺考（直接构造已通过但时段已结束的预约）
    sb = make_user("stat_b")
    past_slot = booking_service.create_slot(db, exam.id, SlotCreate(
        name="过去批次",
        start_time=datetime.now() - timedelta(days=3),
        end_time=datetime.now() - timedelta(days=1),
        capacity=10,
    ))
    from app.models import ExamBooking
    bb = ExamBooking(
        exam_id=exam.id, slot_id=past_slot.id, user_id=sb.id,
        attempt_no=1, booking_type="first", status="approved",
    )
    db.add(bb)
    past_slot.booked_count = 1
    db.commit()

    stats = grade_service.calculate_exam_stats(db, exam.id)
    assert stats["student_count"] == 1
    assert stats["booked_count"] == 2
    assert stats["absent_count"] == 1
    assert stats["first_attempt_count"] == 1
    assert stats["pass_count"] == 1


def test_rank_uses_best_attempt_on_retake(db, make_user, make_question):
    """补考后排名按每人最佳成绩，total 为去重人数"""
    exam = _make_exam(db, require_booking=0, max_attempts=3)
    s1 = make_user("rank_retake_s1")
    s2 = make_user("rank_retake_s2")

    # s1 首考 0 分、补考高分（题目分值固定 5 分，这里构造两次 graded 记录）
    db.add(ExamAttempt(exam_id=exam.id, user_id=s1.id, attempt_no=1,
                       start_time=datetime.now(), submit_time=datetime.now(),
                       score=0, status="graded", is_passed=0))
    db.add(ExamAttempt(exam_id=exam.id, user_id=s1.id, attempt_no=2,
                       start_time=datetime.now(), submit_time=datetime.now(),
                       score=90, status="graded", is_passed=1))
    db.add(ExamAttempt(exam_id=exam.id, user_id=s2.id, attempt_no=1,
                       start_time=datetime.now(), submit_time=datetime.now(),
                       score=80, status="graded", is_passed=1))
    db.commit()

    result = grade_service.get_user_rank(db, s1.id, exam.id)
    assert result["rank"] == 1
    assert result["total"] == 2
