from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ExamCreate(BaseModel):
    title: str
    description: str = ""
    subject_id: int
    exam_type: str = "formal"
    duration_minutes: int = Field(default=60, ge=1)
    total_score: int = Field(default=100, ge=1)
    pass_score: int = Field(default=60, ge=0)
    start_time: datetime | None = None
    end_time: datetime | None = None
    is_random_order: int = 0
    is_option_random: int = 0
    allow_back: int = 1
    anti_cheat_enabled: int = 1
    require_booking: int = 0
    max_attempts: int = Field(default=1, ge=1)


class ExamUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    subject_id: int | None = None
    exam_type: str | None = None
    duration_minutes: int | None = None
    total_score: int | None = None
    pass_score: int | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    is_random_order: int | None = None
    is_option_random: int | None = None
    allow_back: int | None = None
    anti_cheat_enabled: int | None = None
    require_booking: int | None = None
    max_attempts: int | None = Field(default=None, ge=1)
    status: str | None = None


class ExamQuestionAdd(BaseModel):
    question_id: int
    score: int = 5
    order_index: int = 0


class ExamResponse(ORMModel):
    id: int
    title: str
    description: str
    subject_id: int
    exam_type: str
    duration_minutes: int
    total_score: int
    pass_score: int
    start_time: datetime | None
    end_time: datetime | None
    is_random_order: int
    is_option_random: int
    allow_back: int
    anti_cheat_enabled: int
    require_booking: int
    max_attempts: int
    status: str
    created_at: datetime


class ExamDetailResponse(ExamResponse):
    question_count: int = 0


class PaperCreate(BaseModel):
    title: str
    description: str = ""
    subject_id: int
    total_score: int = 100
    question_ids: list[int] = []
    scores: dict[int, int] = {}


class PaperResponse(ORMModel):
    id: int
    title: str
    subject_id: int
    total_score: int
    created_at: datetime


class DifficultyDistribution(BaseModel):
    level: int  # 1-5
    percentage: float  # 0-100


class QuestionTypeDistribution(BaseModel):
    question_type: str
    count: int


class KnowledgePointWeight(BaseModel):
    kp_id: int
    weight: float  # 0-100


class SmartPaperGenRequest(BaseModel):
    title: str
    subject_id: int
    total_score: int = Field(default=100, ge=1)
    duration_minutes: int = 60
    knowledge_point_weights: list[KnowledgePointWeight]
    difficulty_distribution: list[DifficultyDistribution]
    question_type_distribution: list[QuestionTypeDistribution]


class SmartPaperGenResponse(BaseModel):
    paper_id: int
    selected_questions: list[int]
    actual_total_score: int
    warnings: list[str] = []
