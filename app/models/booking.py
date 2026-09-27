from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ExamSlot(Base):
    """考试时段：管理员为每场考试配置可预约的时间窗口与名额"""
    __tablename__ = "exam_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exam_id: Mapped[int] = mapped_column(Integer, ForeignKey("exams.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), default="")  # 批次名称，如“第一批次”
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=0)  # 名额，0 表示不限
    booked_count: Mapped[int] = mapped_column(Integer, default=0)  # 已占用名额（审核通过）
    status: Mapped[str] = mapped_column(String(20), default="open")  # open/closed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    exam = relationship("Exam", back_populates="slots")
    bookings: Mapped[list["ExamBooking"]] = relationship(
        "ExamBooking", back_populates="slot"
    )


class ExamBooking(Base):
    """考试预约 / 补考申请，状态驱动开考资格"""
    __tablename__ = "exam_bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exam_id: Mapped[int] = mapped_column(Integer, ForeignKey("exams.id"), nullable=False, index=True)
    slot_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("exam_slots.id"), nullable=True, index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)  # 第几次考试（1=首考）
    booking_type: Mapped[str] = mapped_column(String(10), default="first")  # first/retake
    # pending 待审核 / approved 已通过 / rejected 已驳回 /
    # cancelled 已取消 / used 已用于开考 / missed 缺考（时段结束未考）
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    apply_reason: Mapped[str] = mapped_column(Text, default="")
    review_comment: Mapped[str] = mapped_column(Text, default="")
    reviewer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    exam = relationship("Exam")
    slot: Mapped[ExamSlot | None] = relationship("ExamSlot", back_populates="bookings")
    user = relationship("User")
