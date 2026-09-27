from datetime import datetime

from pydantic import BaseModel, Field


# ---------- 时段 ----------
class SlotCreate(BaseModel):
    name: str = ""
    start_time: datetime
    end_time: datetime
    capacity: int = Field(default=0, ge=0)
    status: str = "open"


class SlotUpdate(BaseModel):
    name: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    capacity: int | None = Field(default=None, ge=0)
    status: str | None = None


class SlotResponse(BaseModel):
    id: int
    exam_id: int
    name: str
    start_time: datetime
    end_time: datetime
    capacity: int
    booked_count: int
    remaining: int
    status: str
    created_at: datetime


# ---------- 预约 / 补考 ----------
class BookingCreate(BaseModel):
    slot_id: int
    apply_reason: str = ""


class BookingReviewRequest(BaseModel):
    approved: bool
    review_comment: str = ""


class BookingResponse(BaseModel):
    id: int
    exam_id: int
    slot_id: int | None
    user_id: int
    username: str = ""
    real_name: str = ""
    attempt_no: int
    booking_type: str
    status: str
    apply_reason: str
    review_comment: str
    reviewer_id: int | None
    reviewed_at: datetime | None
    created_at: datetime
    slot_name: str = ""
    slot_start: datetime | None = None
    slot_end: datetime | None = None
    exam_title: str = ""


# ---------- 开考资格 ----------
class EligibilityResponse(BaseModel):
    exam_id: int
    require_booking: bool
    can_start: bool
    reason: str = ""
    max_attempts: int
    used_attempts: int
    remaining_attempts: int
    has_passed: bool
    booking: BookingResponse | None = None
