from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models import User, Exam
from app.schemas.booking import (
    SlotCreate, SlotUpdate, SlotResponse,
    BookingCreate, BookingReviewRequest, BookingResponse,
    EligibilityResponse,
)
from app.schemas.common import APIResponse, PageResponse
from app.services import booking_service, exam_service

router = APIRouter(tags=["考试预约与补考"])


# ---------- 时段名额配置（管理员） ----------
@router.post("/exams/{exam_id}/slots", response_model=APIResponse[SlotResponse])
def create_slot(exam_id: int, data: SlotCreate, db: Session = Depends(get_db),
                user: User = Depends(require_roles("admin"))):
    try:
        slot = booking_service.create_slot(db, exam_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return APIResponse(data=SlotResponse(**booking_service.slot_to_dict(slot)))


@router.get("/exams/{exam_id}/slots", response_model=APIResponse[list[SlotResponse]])
def list_slots(exam_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    # 学生只看开放时段；教师/管理员可看全部
    include_closed = user.role in ("admin", "teacher")
    slots = booking_service.list_slots(db, exam_id, include_closed=include_closed)
    return APIResponse(data=[SlotResponse(**booking_service.slot_to_dict(s)) for s in slots])


@router.put("/slots/{slot_id}", response_model=APIResponse[SlotResponse])
def update_slot(slot_id: int, data: SlotUpdate, db: Session = Depends(get_db),
                user: User = Depends(require_roles("admin"))):
    slot = booking_service.get_slot(db, slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="时段不存在")
    try:
        slot = booking_service.update_slot(db, slot, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return APIResponse(data=SlotResponse(**booking_service.slot_to_dict(slot)))


@router.delete("/slots/{slot_id}", response_model=APIResponse)
def delete_slot(slot_id: int, db: Session = Depends(get_db),
                user: User = Depends(require_roles("admin"))):
    slot = booking_service.get_slot(db, slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="时段不存在")
    try:
        booking_service.delete_slot(db, slot)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return APIResponse(data=None)


# ---------- 开考资格 ----------
@router.get("/exams/{exam_id}/eligibility", response_model=APIResponse[EligibilityResponse])
def exam_eligibility(exam_id: int, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    exam = exam_service.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="考试不存在")
    info = booking_service.check_eligibility(db, exam, user.id)
    booking = info.pop("booking", None)
    data = EligibilityResponse(**info)
    if booking:
        data.booking = BookingResponse(
            **booking_service.booking_to_dict(booking)
        )
    return APIResponse(data=data)


# ---------- 学生：申请 / 查询 / 取消 ----------
@router.post("/bookings", response_model=APIResponse[BookingResponse])
def apply_booking(data: BookingCreate, db: Session = Depends(get_db),
                  user: User = Depends(require_roles("student"))):
    slot = booking_service.get_slot(db, data.slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="时段不存在")
    try:
        booking = booking_service.apply_booking(
            db, slot.exam_id, data.slot_id, user.id, data.apply_reason
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return APIResponse(data=BookingResponse(**booking_service.booking_to_dict(booking)))


@router.get("/bookings/my", response_model=APIResponse[list[BookingResponse]])
def my_bookings(exam_id: int | None = None, db: Session = Depends(get_db),
                user: User = Depends(require_roles("student"))):
    bookings = booking_service.list_user_bookings(db, user.id, exam_id)
    return APIResponse(data=[BookingResponse(**booking_service.booking_to_dict(b)) for b in bookings])


@router.post("/bookings/{booking_id}/cancel", response_model=APIResponse[BookingResponse])
def cancel_my_booking(booking_id: int, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    booking = booking_service.get_booking(db, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="预约不存在")
    # 学生只能取消自己的；管理员可强制取消
    if user.role == "student" and booking.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权取消他人的预约")
    if user.role == "teacher" and booking.user_id != user.id:
        raise HTTPException(status_code=403, detail="教师无强制取消权限")
    try:
        booking = booking_service.cancel_booking(db, booking)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return APIResponse(data=BookingResponse(**booking_service.booking_to_dict(booking)))


# ---------- 教师/管理员：审核与列表 ----------
@router.get("/bookings", response_model=APIResponse[PageResponse[BookingResponse]])
def list_bookings(
    exam_id: int | None = None,
    status: str | None = None,
    slot_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher")),
):
    total, items = booking_service.list_bookings(
        db, exam_id=exam_id, status=status, slot_id=slot_id,
        page=page, page_size=page_size,
    )
    return APIResponse(data=PageResponse(
        total=total, page=page, page_size=page_size,
        items=[BookingResponse(**booking_service.booking_to_dict(b)) for b in items],
    ))


@router.get("/bookings/{booking_id}", response_model=APIResponse[BookingResponse])
def get_booking(booking_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    booking = booking_service.get_booking(db, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="预约不存在")
    if user.role == "student" and booking.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权查看该预约")
    return APIResponse(data=BookingResponse(**booking_service.booking_to_dict(booking)))


@router.post("/bookings/{booking_id}/review", response_model=APIResponse[BookingResponse])
def review_booking(booking_id: int, data: BookingReviewRequest,
                   db: Session = Depends(get_db),
                   user: User = Depends(require_roles("admin", "teacher"))):
    booking = booking_service.get_booking(db, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="预约不存在")
    try:
        booking = booking_service.review_booking(
            db, booking, user.id, data.approved, data.review_comment
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return APIResponse(data=BookingResponse(**booking_service.booking_to_dict(booking)))
