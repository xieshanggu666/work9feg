"""考试预约与补考管理服务。

业务流：学生申请（首考/补考）→ 教师审核（通过即占用名额）→ 管理员配置时段名额。
预约状态驱动：开考资格、考试次数限制、成绩统计与证书发放（见 attempt/grade 服务）。
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Exam, ExamSlot, ExamBooking, ExamAttempt
from app.schemas.booking import SlotCreate, SlotUpdate

# 可继续用于开考/占用名额的预约状态
ACTIVE_STATUSES = ("pending", "approved")
FINISHED_ATTEMPT_STATUSES = ("submitted", "graded")


# ---------- 时段管理（管理员） ----------
def create_slot(db: Session, exam_id: int, data: SlotCreate) -> ExamSlot:
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise ValueError("考试不存在")
    if data.end_time <= data.start_time:
        raise ValueError("时段结束时间必须晚于开始时间")
    slot = ExamSlot(exam_id=exam_id, **data.model_dump())
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


def list_slots(db: Session, exam_id: int, include_closed: bool = True) -> list[ExamSlot]:
    sync_missed(db, exam_id=exam_id)
    query = db.query(ExamSlot).filter(ExamSlot.exam_id == exam_id)
    if not include_closed:
        query = query.filter(ExamSlot.status == "open")
    return query.order_by(ExamSlot.start_time.asc()).all()


def get_slot(db: Session, slot_id: int) -> ExamSlot | None:
    return db.query(ExamSlot).filter(ExamSlot.id == slot_id).first()


def update_slot(db: Session, slot: ExamSlot, data: SlotUpdate) -> ExamSlot:
    payload = data.model_dump(exclude_unset=True)
    new_start = payload.get("start_time", slot.start_time)
    new_end = payload.get("end_time", slot.end_time)
    if new_end <= new_start:
        raise ValueError("时段结束时间必须晚于开始时间")
    new_capacity = payload.get("capacity", slot.capacity)
    if new_capacity and slot.booked_count > new_capacity:
        raise ValueError(f"名额不能小于已预约人数（{slot.booked_count} 人）")
    for field, value in payload.items():
        setattr(slot, field, value)
    db.commit()
    db.refresh(slot)
    return slot


def delete_slot(db: Session, slot: ExamSlot) -> None:
    used = (
        db.query(ExamBooking)
        .filter(ExamBooking.slot_id == slot.id, ExamBooking.status.in_(ACTIVE_STATUSES))
        .count()
    )
    if used:
        raise ValueError("该时段仍有待审核或已通过的预约，无法删除")
    db.delete(slot)
    db.commit()


def slot_remaining(slot: ExamSlot) -> int:
    """剩余名额，capacity=0 表示不限"""
    if slot.capacity == 0:
        return 999999
    return max(0, slot.capacity - slot.booked_count)


# ---------- 预约 / 补考申请（学生） ----------
def _counts(db: Session, exam_id: int, user_id: int) -> dict:
    """统计学生在某场考试的次数情况。

    used: 已消耗的考试次数 = 已交卷次数 + 缺考次数
    """
    graded = (
        db.query(ExamAttempt)
        .filter(
            ExamAttempt.exam_id == exam_id,
            ExamAttempt.user_id == user_id,
            ExamAttempt.status.in_(FINISHED_ATTEMPT_STATUSES),
        )
        .count()
    )
    missed = (
        db.query(ExamBooking)
        .filter(
            ExamBooking.exam_id == exam_id,
            ExamBooking.user_id == user_id,
            ExamBooking.status == "missed",
        )
        .count()
    )
    has_passed = (
        db.query(ExamAttempt)
        .filter(
            ExamAttempt.exam_id == exam_id,
            ExamAttempt.user_id == user_id,
            ExamAttempt.status == "graded",
            ExamAttempt.is_passed == 1,
        )
        .first()
        is not None
    )
    in_progress = (
        db.query(ExamAttempt)
        .filter(
            ExamAttempt.exam_id == exam_id,
            ExamAttempt.user_id == user_id,
            ExamAttempt.status == "in_progress",
        )
        .first()
    )
    return {
        "graded": graded,
        "missed": missed,
        "used": graded + missed,
        "has_passed": has_passed,
        "in_progress": in_progress,
    }


def sync_missed(db: Session, exam_id: int | None = None,
                user_id: int | None = None) -> int:
    """把时段已结束仍未开考的已通过预约标记为缺考。返回更新条数。"""
    now = datetime.now()
    query = (
        db.query(ExamBooking)
        .join(ExamSlot, ExamBooking.slot_id == ExamSlot.id)
        .filter(ExamBooking.status == "approved", ExamSlot.end_time < now)
    )
    if exam_id is not None:
        query = query.filter(ExamBooking.exam_id == exam_id)
    if user_id is not None:
        query = query.filter(ExamBooking.user_id == user_id)
    bookings = query.all()
    for b in bookings:
        b.status = "missed"
    if bookings:
        db.commit()
    return len(bookings)


def apply_booking(db: Session, exam_id: int, slot_id: int,
                  user_id: int, reason: str = "") -> ExamBooking:
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise ValueError("考试不存在")
    if exam.status != "published":
        raise ValueError("考试未发布，暂不能预约")
    if not exam.require_booking:
        raise ValueError("该考试无需预约，可直接参加")

    slot = get_slot(db, slot_id)
    if not slot or slot.exam_id != exam_id:
        raise ValueError("预约时段不存在")
    if slot.status != "open":
        raise ValueError("该时段已关闭预约")
    if slot.end_time <= datetime.now():
        raise ValueError("该时段已结束")
    if slot.capacity and slot.booked_count >= slot.capacity:
        raise ValueError("该时段名额已满")

    counts = _counts(db, exam_id, user_id)
    if counts["has_passed"]:
        raise ValueError("您已通过该考试，无需再次预约")
    if counts["in_progress"]:
        raise ValueError("您有一场正在进行中的考试，请先完成交卷")

    active = (
        db.query(ExamBooking)
        .filter(
            ExamBooking.exam_id == exam_id,
            ExamBooking.user_id == user_id,
            ExamBooking.status.in_(ACTIVE_STATUSES),
        )
        .first()
    )
    if active:
        raise ValueError("您已有待审核或已通过的预约，请勿重复申请")

    next_attempt = counts["used"] + 1
    if next_attempt > exam.max_attempts:
        raise ValueError(f"该考试最多允许参加 {exam.max_attempts} 次，已达上限")

    booking = ExamBooking(
        exam_id=exam_id,
        slot_id=slot.id,
        user_id=user_id,
        attempt_no=next_attempt,
        booking_type="first" if counts["graded"] == 0 and counts["missed"] == 0 else "retake",
        status="pending",
        apply_reason=reason,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


def review_booking(db: Session, booking: ExamBooking, reviewer_id: int,
                   approved: bool, comment: str = "") -> ExamBooking:
    """教师审核：通过即占用时段名额，并复核次数/名额。"""
    if booking.status != "pending":
        raise ValueError("仅待审核的预约可以审核")

    booking.reviewer_id = reviewer_id
    booking.review_comment = comment
    booking.reviewed_at = datetime.now()

    if not approved:
        booking.status = "rejected"
        db.commit()
        db.refresh(booking)
        return booking

    exam = db.query(Exam).filter(Exam.id == booking.exam_id).first()
    slot = booking.slot
    counts = _counts(db, booking.exam_id, booking.user_id)

    if counts["has_passed"]:
        raise ValueError("该学生已通过考试，无需通过预约")
    if counts["used"] + 1 > (exam.max_attempts if exam else booking.attempt_no):
        raise ValueError("该学生考试次数已达上限，无法通过")
    if not slot:
        raise ValueError("预约时段不存在")
    if slot.status != "open":
        raise ValueError("该时段已关闭，无法通过")
    if slot.capacity and slot.booked_count >= slot.capacity:
        raise ValueError("该时段名额已满，无法通过")

    # 审核时再次确认序号（申请后可能产生缺考等变化）
    booking.attempt_no = counts["used"] + 1
    booking.booking_type = "first" if counts["used"] == 0 else "retake"
    booking.status = "approved"
    slot.booked_count += 1
    db.commit()
    db.refresh(booking)
    return booking


def cancel_booking(db: Session, booking: ExamBooking) -> ExamBooking:
    """取消预约：学生取消自己的，或管理员强制取消。已通过的退回名额。"""
    if booking.status not in ACTIVE_STATUSES:
        raise ValueError("仅待审核或已通过的预约可以取消")
    if booking.status == "approved" and booking.slot:
        booking.slot.booked_count = max(0, booking.slot.booked_count - 1)
    booking.status = "cancelled"
    db.commit()
    db.refresh(booking)
    return booking


def get_booking(db: Session, booking_id: int) -> ExamBooking | None:
    return db.query(ExamBooking).filter(ExamBooking.id == booking_id).first()


def list_bookings(db: Session, exam_id: int | None = None,
                  status: str | None = None, slot_id: int | None = None,
                  page: int = 1, page_size: int = 20):
    """教师/管理员视角的预约列表。"""
    sync_missed(db, exam_id=exam_id)
    query = db.query(ExamBooking)
    if exam_id is not None:
        query = query.filter(ExamBooking.exam_id == exam_id)
    if status:
        query = query.filter(ExamBooking.status == status)
    if slot_id is not None:
        query = query.filter(ExamBooking.slot_id == slot_id)
    total = query.count()
    items = (
        query.order_by(ExamBooking.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return total, items


def list_user_bookings(db: Session, user_id: int,
                       exam_id: int | None = None) -> list[ExamBooking]:
    sync_missed(db, exam_id=exam_id, user_id=user_id)
    query = db.query(ExamBooking).filter(ExamBooking.user_id == user_id)
    if exam_id is not None:
        query = query.filter(ExamBooking.exam_id == exam_id)
    return query.order_by(ExamBooking.created_at.desc()).all()


# ---------- 开考资格 ----------
def check_eligibility(db: Session, exam: Exam, user_id: int) -> dict:
    """预约状态驱动开考资格，返回资格明细供 API/前端使用。"""
    sync_missed(db, exam_id=exam.id, user_id=user_id)
    counts = _counts(db, exam.id, user_id)
    used = counts["used"]

    result = {
        "exam_id": exam.id,
        "require_booking": bool(exam.require_booking),
        "can_start": False,
        "reason": "",
        "max_attempts": exam.max_attempts,
        "used_attempts": used,
        "remaining_attempts": max(0, exam.max_attempts - used),
        "has_passed": counts["has_passed"],
        "booking": None,
    }

    if exam.status != "published":
        result["reason"] = "考试未发布"
        return result
    if counts["has_passed"]:
        result["reason"] = "您已通过该考试，无需再次参加"
        return result
    if counts["in_progress"]:
        result["can_start"] = True
        result["reason"] = "您有一场进行中的考试"
        return result
    if used >= exam.max_attempts:
        result["reason"] = (
            f"已达最大考试次数（{exam.max_attempts} 次）"
            + ("，如有需要请联系教师申请补考" if exam.require_booking else "")
        )
        return result

    if not exam.require_booking:
        result["can_start"] = True
        return result

    booking = (
        db.query(ExamBooking)
        .filter(
            ExamBooking.exam_id == exam.id,
            ExamBooking.user_id == user_id,
            ExamBooking.status.in_(("approved", "used")),
        )
        .order_by(ExamBooking.id.desc())
        .first()
    )
    if not booking:
        pending = (
            db.query(ExamBooking)
            .filter(
                ExamBooking.exam_id == exam.id,
                ExamBooking.user_id == user_id,
                ExamBooking.status == "pending",
            )
            .first()
        )
        result["reason"] = "您的预约正在审核中，请等待教师审核" if pending else "请先预约考试时段"
        return result

    result["booking"] = booking
    if booking.status == "used":
        result["reason"] = "该预约已用于考试"
        return result

    slot = booking.slot
    now = datetime.now()
    if not slot:
        result["reason"] = "预约时段不存在"
        return result
    if slot.status != "open":
        result["reason"] = "预约时段已关闭"
        return result
    if now < slot.start_time:
        result["reason"] = f"未到预约开考时间（{slot.start_time:%Y-%m-%d %H:%M}）"
        return result
    if now > slot.end_time:
        result["reason"] = "预约时段已结束，本次预约按缺考处理"
        return result
    if booking.attempt_no != used + 1:
        result["reason"] = "预约场次与当前考试次数不一致，请重新申请"
        return result

    result["can_start"] = True
    return result


def consume_booking(db: Session, booking: ExamBooking) -> None:
    """开考成功后把预约置为已使用。"""
    booking.status = "used"
    db.commit()


# ---------- 响应序列化 ----------
def booking_to_dict(booking: ExamBooking) -> dict:
    slot = booking.slot
    return {
        "id": booking.id,
        "exam_id": booking.exam_id,
        "slot_id": booking.slot_id,
        "user_id": booking.user_id,
        "username": booking.user.username if booking.user else "",
        "real_name": booking.user.real_name if booking.user else "",
        "attempt_no": booking.attempt_no,
        "booking_type": booking.booking_type,
        "status": booking.status,
        "apply_reason": booking.apply_reason,
        "review_comment": booking.review_comment,
        "reviewer_id": booking.reviewer_id,
        "reviewed_at": booking.reviewed_at,
        "created_at": booking.created_at,
        "slot_name": slot.name if slot else "",
        "slot_start": slot.start_time if slot else None,
        "slot_end": slot.end_time if slot else None,
        "exam_title": booking.exam.title if booking.exam else "",
    }


def slot_to_dict(slot: ExamSlot) -> dict:
    return {
        "id": slot.id,
        "exam_id": slot.exam_id,
        "name": slot.name,
        "start_time": slot.start_time,
        "end_time": slot.end_time,
        "capacity": slot.capacity,
        "booked_count": slot.booked_count,
        "remaining": slot_remaining(slot),
        "status": slot.status,
        "created_at": slot.created_at,
    }
