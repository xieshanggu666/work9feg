from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models import User
from app.schemas.grade import (
    ExamStatsResponse, QuestionStatsResponse, RankResponse,
    LeaderboardItem, CertificateResponse,
)
from app.schemas.common import APIResponse
from app.services import grade_service

router = APIRouter(prefix="/grades", tags=["成绩统计"])


@router.get("/stats/{exam_id}", response_model=APIResponse[ExamStatsResponse])
def exam_stats(exam_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    stats = grade_service.calculate_exam_stats(db, exam_id)
    return APIResponse(data=ExamStatsResponse(**stats))


@router.get("/question-stats/{question_id}", response_model=APIResponse[QuestionStatsResponse])
def question_stats(question_id: int, db: Session = Depends(get_db),
                   user: User = Depends(require_roles("admin", "teacher"))):
    stats = grade_service.calculate_question_stats(db, question_id)
    return APIResponse(data=QuestionStatsResponse(
        question_id=stats.question_id,
        total_attempts=stats.total_attempts,
        correct_count=stats.correct_count,
        wrong_count=stats.wrong_count,
        accuracy=round(stats.correct_count / stats.total_attempts * 100, 1) if stats.total_attempts else 0,
        difficulty_actual=stats.difficulty_actual,
        discrimination_actual=stats.discrimination_actual,
    ))


@router.get("/rank/{exam_id}", response_model=APIResponse[RankResponse])
def my_rank(exam_id: int, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    try:
        rank_info = grade_service.get_user_rank(db, user.id, exam_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return APIResponse(data=RankResponse(**rank_info))


@router.get("/leaderboard/{exam_id}", response_model=APIResponse[list[LeaderboardItem]])
def leaderboard(exam_id: int, limit: int = 20, db: Session = Depends(get_db)):
    items = grade_service.get_leaderboard(db, exam_id, limit)
    return APIResponse(data=[LeaderboardItem(**i) for i in items])


@router.get("/certificates", response_model=APIResponse[list[CertificateResponse]])
def my_certificates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    certs = grade_service.list_certificates(db, user.id)
    return APIResponse(data=[CertificateResponse.model_validate(c) for c in certs])


@router.post("/certificates/{exam_id}/generate", response_model=APIResponse[CertificateResponse])
def generate_certificate(exam_id: int, db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    try:
        cert = grade_service.generate_certificate(db, user.id, exam_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return APIResponse(data=CertificateResponse.model_validate(cert))
