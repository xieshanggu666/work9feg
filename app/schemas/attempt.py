from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel
from app.schemas.question import QuestionResponse  # noqa: F401（保留对外类型引用）


class ExamQuestionBrief(BaseModel):
    exam_question_id: int
    question_id: int
    question_type: str
    content: str
    score: int
    options: list[dict] = []


class SavedAnswerBrief(BaseModel):
    """已保存到服务端的单题答案（刷新/重连恢复用）"""
    question_id: int
    user_answer: str
    time_spent_seconds: int = 0
    version: int = 0


class ExamStartResponse(BaseModel):
    attempt_id: int
    exam_id: int
    title: str
    duration_minutes: int
    total_score: int
    start_time: datetime
    questions: list[ExamQuestionBrief]
    # 恢复与多端同步
    status: str = "in_progress"          # in_progress / graded
    answers: list[SavedAnswerBrief] = []
    answer_version: int = 0
    deadline: datetime | None = None    # 服务端交卷截止时刻
    server_time: datetime | None = None  # 响应生成时的服务端时钟（用于校准时钟偏移）


class AnswerSubmit(BaseModel):
    question_id: int
    user_answer: str
    time_spent_seconds: int = 0
    # 客户端上次同步到的该题版本号，用于多端冲突检测
    base_version: int = 0


class ExamSubmitRequest(BaseModel):
    answers: list[AnswerSubmit] = []
    # manual=手动交卷 timeout=到时自动交卷 forced=防作弊强制交卷
    submit_type: str = "manual"


class AnswerSaveRequest(BaseModel):
    answers: list[AnswerSubmit]


class AnswerConflictItem(BaseModel):
    question_id: int
    server_answer: str
    server_version: int


class AnswerSaveResponse(BaseModel):
    answer_version: int
    saved_count: int
    conflicts: list[AnswerConflictItem] = []


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
    # 重复提交时返回 already=True，前端可直接当作交卷成功
    already: bool = False
    submit_type: str = "manual"
