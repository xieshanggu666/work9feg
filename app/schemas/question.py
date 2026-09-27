from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class SubjectCreate(BaseModel):
    name: str
    code: str
    description: str = ""


class SubjectResponse(ORMModel):
    id: int
    name: str
    code: str
    description: str


class KnowledgePointCreate(BaseModel):
    name: str
    parent_id: int | None = None
    subject_id: int
    description: str = ""


class KnowledgePointResponse(ORMModel):
    id: int
    name: str
    parent_id: int | None
    subject_id: int
    children: list["KnowledgePointResponse"] = []


class TagCreate(BaseModel):
    name: str
    color: str = "#6c63ff"


class TagResponse(ORMModel):
    id: int
    name: str
    color: str


class QuestionOptionCreate(BaseModel):
    content: str
    is_correct: int = 0
    order_index: int = 0


class QuestionOptionResponse(ORMModel):
    id: int
    content: str
    is_correct: int
    order_index: int


class QuestionCreate(BaseModel):
    question_type: str
    content: str
    analysis: str = ""
    difficulty: int = Field(ge=1, le=5)
    knowledge_point_id: int
    subject_id: int
    options: list[QuestionOptionCreate] = []
    tag_ids: list[int] = []


class QuestionUpdate(BaseModel):
    question_type: str | None = None
    content: str | None = None
    analysis: str | None = None
    difficulty: int | None = None
    knowledge_point_id: int | None = None
    options: list[QuestionOptionCreate] | None = None
    tag_ids: list[int] | None = None


class QuestionResponse(ORMModel):
    id: int
    question_type: str
    content: str
    analysis: str
    difficulty: int
    discrimination: float
    knowledge_point_id: int
    subject_id: int
    created_at: datetime
    options: list[QuestionOptionResponse]
    tags: list[TagResponse]


class QuestionBatchImport(BaseModel):
    questions: list[QuestionCreate]


class QuestionListResponse(ORMModel):
    id: int
    question_type: str
    content: str
    difficulty: int
    knowledge_point_id: int
    subject_id: int
