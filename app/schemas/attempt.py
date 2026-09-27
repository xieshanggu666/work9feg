from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel
from app.schemas.question import QuestionResponse


class ExamQuestionBrief(BaseModel):
    exam_question_id: int
    question_id: int
    question_type: str
    content: str
    score: int
    options: list[dict] = []


class ExamStartResponse(BaseModel):
    attempt_id: int
    exam_id: int
    title: str
    duration_minutes: int
    total_score: int
    start_time: datetime
    questions: list[ExamQuestionBrief]


class AnswerSubmit(BaseModel):
    question_id: int
    user_answer: str
    time_spent_seconds: int = 0


class ExamSubmitRequest(BaseModel):
    answers: list[AnswerSubmit] = []


class ExamAnswerResponse(ORMModel):
    id: int
    question_id: int
    user_answer: str
    is_correct: int
    score: float
    time_spent_seconds: int


class ExamAttemptResponse(ORMModel):
    id: int
    exam_id: int
    user_id: int
    start_time: datetime
    submit_time: datetime | None
    score: float
    is_passed: int
    status: str
    screen_switch_count: int
    cheat_warning_count: int


class ExamResultResponse(BaseModel):
    attempt_id: int
    exam_id: int
    score: float
    total_score: int
    is_passed: bool
    submit_time: datetime | None
    answers: list[ExamAnswerResponse]
    rank: int | None = None
    percentile: float | None = None
