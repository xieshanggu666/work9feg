from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Certificate(Base):
    __tablename__ = "certificates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    exam_id: Mapped[int] = mapped_column(Integer, ForeignKey("exams.id"), nullable=False)
    certificate_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    issue_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    is_valid: Mapped[int] = mapped_column(Integer, default=1)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_reason: Mapped[str] = mapped_column(String(255), default="")

    user = relationship("User")
    exam = relationship("Exam")
