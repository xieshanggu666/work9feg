from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ExamAttempt(Base):
    __tablename__ = "exam_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exam_id: Mapped[int] = mapped_column(Integer, ForeignKey("exams.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    booking_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("exam_bookings.id"), nullable=True, index=True
    )
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)  # 第几次考试（补考次数递增）
    start_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    submit_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    score: Mapped[float] = mapped_column(default=0.0)
    is_passed: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="in_progress")  # in_progress/submitted/graded
    ip_address: Mapped[str] = mapped_column(String(50), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    cheat_warning_count: Mapped[int] = mapped_column(Integer, default=0)
    screen_switch_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    exam: Mapped["Exam"] = relationship("Exam", back_populates="attempts")
    user: Mapped["User"] = relationship("User", back_populates="attempts")
    booking = relationship("ExamBooking")
    answers: Mapped[list["ExamAnswer"]] = relationship(
        "ExamAnswer", back_populates="attempt", cascade="all, delete-orphan"
    )


class ExamAnswer(Base):
    """答题记录同时充当「自动保存的草稿」：开考后逐题 upsert，交卷时原地评分。"""
    __tablename__ = "exam_answers"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="ux_answers_attempt_question"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attempt_id: Mapped[int] = mapped_column(Integer, ForeignKey("exam_attempts.id"), nullable=False, index=True)
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("questions.id"), nullable=False)
    user_answer: Mapped[str] = mapped_column(Text, default="")
    is_correct: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(default=0.0)
    time_spent_seconds: Mapped[int] = mapped_column(Integer, default=0)
    # 乐观锁版本号：每次保存 +1，用于多端修改冲突检测
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    attempt: Mapped[ExamAttempt] = relationship("ExamAttempt", back_populates="answers")
    question = relationship("Question")
