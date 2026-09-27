from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User, Exam, ExamAttempt
from app.schemas.attempt import (
    ExamStartResponse, ExamQuestionBrief, ExamSubmitRequest, ExamResultResponse,
)
from app.schemas.common import APIResponse
from app.services import attempt_service, anti_cheat_service, grade_service

router = APIRouter(prefix="/attempts", tags=["考试答题"])


@router.post("/{exam_id}/start", response_model=APIResponse[ExamStartResponse])
def start_exam(exam_id: int, request: Request, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="考试不存在")
    if exam.status != "published":
        raise HTTPException(status_code=400, detail="考试未发布")

    client_ip = request.client.host if request.client else ""
    user_agent = request.headers.get("user-agent", "")
    try:
        attempt = attempt_service.start_exam(db, exam, user.id, client_ip, user_agent)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    questions = attempt_service._collect_exam_questions(db, exam)
    return APIResponse(data=ExamStartResponse(
        attempt_id=attempt.id,
        exam_id=exam.id,
        title=exam.title,
        duration_minutes=exam.duration_minutes,
        total_score=exam.total_score,
        start_time=attempt.start_time,
        questions=[ExamQuestionBrief(**q) for q in questions],
    ))


@router.post("/{attempt_id}/submit", response_model=APIResponse[ExamResultResponse])
def submit_exam(attempt_id: int, data: ExamSubmitRequest, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    attempt = attempt_service.get_attempt(db, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="考试记录不存在")
    if attempt.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作他人的考试记录")
    if attempt.status == "graded":
        raise HTTPException(status_code=400, detail="该考试已提交")

    # 答题用时异常检测
    for a in data.answers:
        if anti_cheat_service.validate_answer_time(db, attempt, a.question_id, a.time_spent_seconds):
            attempt.cheat_warning_count += 1

    try:
        attempt = attempt_service.submit_exam(db, attempt, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
    answers = attempt_service.get_attempt_result(db, attempt)

    rank_info = None
    try:
        rank_info = grade_service.get_user_rank(
            db, user.id, attempt.exam_id, attempt_id=attempt.id
        )
    except ValueError:
        pass

    # 预约/补考联动：通过则自动发放证书
    grade_service.auto_issue_certificate(db, attempt)

    from app.schemas.attempt import ExamAnswerResponse
    return APIResponse(data=ExamResultResponse(
        attempt_id=attempt.id,
        exam_id=attempt.exam_id,
        score=attempt.score,
        total_score=exam.total_score if exam else 0,
        is_passed=bool(attempt.is_passed),
        submit_time=attempt.submit_time,
        answers=[ExamAnswerResponse.model_validate(a) for a in answers],
        rank=rank_info["rank"] if rank_info else None,
        percentile=rank_info["percentile"] if rank_info else None,
    ))


@router.post("/{attempt_id}/screen-switch", response_model=APIResponse[dict])
def screen_switch(attempt_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """前端在检测到用户切屏时上报一次"""
    attempt = attempt_service.get_attempt(db, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="考试记录不存在")
    if attempt.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作他人的考试记录")

    force_submit = anti_cheat_service.record_screen_switch(db, attempt)
    return APIResponse(data={
        "warning": attempt.cheat_warning_count,
        "force_submit": force_submit,
    })
