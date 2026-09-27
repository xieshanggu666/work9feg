from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Exam(Base):
    __tablename__ = "exams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    subject_id: Mapped[int] = mapped_column(Integer, ForeignKey("subjects.id"), nullable=False)
    exam_type: Mapped[str] = mapped_column(String(20), default="formal")  # formal/practice/mock
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    total_score: Mapped[int] = mapped_column(Integer, default=100)
    pass_score: Mapped[int] = mapped_column(Integer, default=60)
    start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_random_order: Mapped[int] = mapped_column(Integer, default=0)
    is_option_random: Mapped[int] = mapped_column(Integer, default=0)
    allow_back: Mapped[int] = mapped_column(Integer, default=1)
    anti_cheat_enabled: Mapped[int] = mapped_column(Integer, default=1)
    require_booking: Mapped[int] = mapped_column(Integer, default=0)  # 是否必须预约才能开考
    max_attempts: Mapped[int] = mapped_column(Integer, default=1)  # 允许考试次数（1=仅首考，>1 支持补考）
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft/published/ended
    created_by: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    subject = relationship("Subject")
    questions: Mapped[list["ExamQuestion"]] = relationship(
        "ExamQuestion", back_populates="exam", cascade="all, delete-orphan", order_by="ExamQuestion.order_index"
    )
    attempts = relationship("ExamAttempt", back_populates="exam")
    slots: Mapped[list["ExamSlot"]] = relationship(
        "ExamSlot", cascade="all, delete-orphan", order_by="ExamSlot.start_time"
    )


class ExamQuestion(Base):
    __tablename__ = "exam_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exam_id: Mapped[int] = mapped_column(Integer, ForeignKey("exams.id"), nullable=False, index=True)
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("questions.id"), nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=5)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    exam: Mapped[Exam] = relationship("Exam", back_populates="questions")
    question = relationship("Question")


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    subject_id: Mapped[int] = mapped_column(Integer, ForeignKey("subjects.id"), nullable=False)
    total_score: Mapped[int] = mapped_column(Integer, default=100)
    created_by: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    subject = relationship("Subject")
    questions: Mapped[list["PaperQuestion"]] = relationship(
        "PaperQuestion", back_populates="paper", cascade="all, delete-orphan", order_by="PaperQuestion.order_index"
    )


class PaperQuestion(Base):
    __tablename__ = "paper_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(Integer, ForeignKey("papers.id"), nullable=False, index=True)
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("questions.id"), nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=5)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    paper: Mapped[Paper] = relationship("Paper", back_populates="questions")
    question = relationship("Question")
