from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class ExamStatsResponse(BaseModel):
    exam_id: int
    attempt_count: int
    avg_score: float
    max_score: float
    min_score: float
    pass_rate: float
    distribution: dict[str, int]  # {"0-59": n, "60-69": n, ...}
    # 人数维度（补考时一人多次只计 1 人）
    student_count: int = 0
    pass_count: int = 0
    # 预约 / 到考 / 缺考
    booked_count: int = 0
    attended_count: int = 0
    attendance_rate: float = 0.0
    absent_count: int = 0
    # 补考维度
    first_attempt_count: int = 0
    retake_attempt_count: int = 0
    retake_pass_count: int = 0
    retake_pass_rate: float = 0.0


class QuestionStatsResponse(BaseModel):
    question_id: int
    total_attempts: int
    correct_count: int
    wrong_count: int
    accuracy: float
    difficulty_actual: float
    discrimination_actual: float


class RankResponse(BaseModel):
    user_id: int
    exam_id: int
    score: float
    rank: int
    total: int
    percentile: float


class LeaderboardItem(BaseModel):
    user_id: int
    username: str
    real_name: str
    score: float
    rank: int
    submit_time: datetime | None


class CertificateResponse(ORMModel):
    id: int
    certificate_no: str
    exam_id: int
    score: float
    issue_date: datetime
    is_valid: int
