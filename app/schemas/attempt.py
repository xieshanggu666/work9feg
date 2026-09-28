from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel
from app.schemas.question import QuestionResponse  # noqa: F401  保留对外类型兼容


class ExamQuestionBrief(BaseModel):
    exam_question_id: int
    question_id: int
    question_type: str
    content: str
    score: int
    options: list[dict] = []


class SavedAnswer(BaseModel):
    """恢复答题时回传的已保存答案（含乐观锁版本号）。"""
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
    # 服务端时钟与截止时刻，前端据此校准倒计时（不信任本机时间）
    server_time: datetime
    deadline: datetime
    # 进行中的考试：in_progress；若该场考试已交卷则为 graded
    status: str = "in_progress"
    questions: list[ExamQuestionBrief] = []
    answers: list[SavedAnswer] = []


class AnswerSubmit(BaseModel):
    question_id: int
    user_answer: str
    time_spent_seconds: int = 0


class AnswerSave(BaseModel):
    """自动保存单题答案。base_version 为客户端上次同步到的版本号。"""
    question_id: int
    user_answer: str = ""
    time_spent_seconds: int | None = None
    base_version: int = 0


class ExamAutosaveRequest(BaseModel):
    answers: list[AnswerSave] = []


class SavedAnswerResult(BaseModel):
    question_id: int
    user_answer: str
    time_spent_seconds: int
    version: int


class ConflictItem(BaseModel):
    question_id: int
    server_answer: str
    server_version: int
    client_answer: str


class ExamAutosaveResponse(BaseModel):
    attempt_id: int
    status: str  # in_progress / graded（到时已由服务端交卷）
    server_time: datetime
    deadline: datetime
    saved: list[SavedAnswerResult] = []
    # 保存成功的题目最新版本，供客户端更新本地基准
    versions: dict[str, int] = {}
    # 多端修改冲突：客户端基准版本落后于服务端当前版本
    conflicts: list[ConflictItem] = []


class ExamSubmitRequest(BaseModel):
    answers: list[AnswerSubmit] = []
    # 幂等令牌：同一令牌重复请求只评分一次（双端/重试共用）
    idempotency_key: str | None = None


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
