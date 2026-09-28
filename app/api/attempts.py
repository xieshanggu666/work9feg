from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User, Exam, ExamAttempt
from app.schemas.attempt import (
    ExamStartResponse, ExamQuestionBrief, ExamSubmitRequest, ExamResultResponse,
    AnswerSaveRequest, AnswerSaveResponse, AnswerConflictItem, SavedAnswerBrief,
    ExamAnswerResponse,
)
from app.schemas.common import APIResponse
from app.services import attempt_service, anti_cheat_service, grade_service

router = APIRouter(prefix="/attempts", tags=["考试答题"])


def _build_result(db: Session, attempt: ExamAttempt, exam: Exam | None,
                  already: bool = False) -> ExamResultResponse:
    answers = attempt_service.get_attempt_result(db, attempt)
    rank_info = None
    try:
        rank_info = grade_service.get_user_rank(
            db, attempt.user_id, attempt.exam_id, attempt_id=attempt.id
        )
    except ValueError:
        pass
    return ExamResultResponse(
        attempt_id=attempt.id,
        exam_id=attempt.exam_id,
        score=attempt.score,
        total_score=exam.total_score if exam else 0,
        is_passed=bool(attempt.is_passed),
        submit_time=attempt.submit_time,
        answers=[ExamAnswerResponse.model_validate(a) for a in answers],
        rank=rank_info["rank"] if rank_info else None,
        percentile=rank_info["percentile"] if rank_info else None,
        already=already,
        submit_type=attempt.submit_type or "manual",
    )


@router.post("/{exam_id}/start", response_model=APIResponse[ExamStartResponse])
def start_exam(exam_id: int, request: Request, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """开考 / 恢复考试。

    进行中的考试返回原记录并带上已保存答案、服务端截止时刻；
    刷新或重连后前端据此恢复答案与剩余时间。
    若该场考试已到时，服务端先按已保存答案自动交卷，再按规则决定能否开新一场。
    """
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

    # 恢复前先处理到时自动交卷
    attempt_service.auto_submit_if_expired(db, attempt)
    if attempt.status == "graded":
        # 已被自动交卷：前端直接跳转结果页
        data = ExamStartResponse(
            attempt_id=attempt.id,
            exam_id=exam.id,
            title=exam.title,
            duration_minutes=exam.duration_minutes,
            total_score=exam.total_score,
            start_time=attempt.start_time,
            questions=[],
            status="graded",
            deadline=attempt_service.get_deadline(attempt, exam),
            server_time=datetime.now(),
        )
        return APIResponse(data=data)

    questions = attempt_service._collect_exam_questions(db, exam)
    saved = attempt_service.get_saved_answers(db, attempt)
    return APIResponse(data=ExamStartResponse(
        attempt_id=attempt.id,
        exam_id=exam.id,
        title=exam.title,
        duration_minutes=exam.duration_minutes,
        total_score=exam.total_score,
        start_time=attempt.start_time,
        questions=[ExamQuestionBrief(**q) for q in questions],
        status=attempt.status,
        answers=[
            SavedAnswerBrief(
                question_id=a.question_id,
                user_answer=a.user_answer,
                time_spent_seconds=a.time_spent_seconds,
                version=a.version,
            )
            for a in saved
        ],
        answer_version=attempt.answer_version,
        deadline=attempt_service.get_deadline(attempt, exam),
        server_time=datetime.now(),
    ))


@router.get("/{attempt_id}/resume", response_model=APIResponse[ExamStartResponse])
def resume_exam(attempt_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """重连恢复：返回题目、已保存答案、剩余时间；若已到时则先自动交卷。"""
    attempt = attempt_service.get_attempt(db, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="考试记录不存在")
    if attempt.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作他人的考试记录")

    exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
    attempt_service.auto_submit_if_expired(db, attempt)

    if attempt.status == "graded":
        return APIResponse(data=ExamStartResponse(
            attempt_id=attempt.id,
            exam_id=attempt.exam_id,
            title=exam.title if exam else "",
            duration_minutes=exam.duration_minutes if exam else 0,
            total_score=exam.total_score if exam else 0,
            start_time=attempt.start_time,
            questions=[],
            status="graded",
            deadline=attempt_service.get_deadline(attempt, exam) if exam else None,
            server_time=datetime.now(),
        ))

    questions = attempt_service._collect_exam_questions(db, exam)
    saved = attempt_service.get_saved_answers(db, attempt)
    return APIResponse(data=ExamStartResponse(
        attempt_id=attempt.id,
        exam_id=exam.id,
        title=exam.title,
        duration_minutes=exam.duration_minutes,
        total_score=exam.total_score,
        start_time=attempt.start_time,
        questions=[ExamQuestionBrief(**q) for q in questions],
        status=attempt.status,
        answers=[
            SavedAnswerBrief(
                question_id=a.question_id,
                user_answer=a.user_answer,
                time_spent_seconds=a.time_spent_seconds,
                version=a.version,
            )
            for a in saved
        ],
        answer_version=attempt.answer_version,
        deadline=attempt_service.get_deadline(attempt, exam),
        server_time=datetime.now(),
    ))


@router.put("/{attempt_id}/answers", response_model=APIResponse[AnswerSaveResponse])
def save_answers(attempt_id: int, data: AnswerSaveRequest, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """自动保存答案到服务端（防抖/定时调用）。

    - 已到时：按已保存答案自动交卷，返回 409，前端跳转结果；
    - 多端冲突：在 conflicts 中给出服务端版本，客户端决定合并（字段级最后写入胜出）。
    """
    attempt = attempt_service.get_attempt(db, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="考试记录不存在")
    if attempt.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作他人的考试记录")

    if attempt_service.auto_submit_if_expired(db, attempt):
        raise HTTPException(status_code=409, detail="考试时间到，系统已自动交卷")

    try:
        result = attempt_service.save_answers(db, attempt, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return APIResponse(data=AnswerSaveResponse(
        answer_version=result["answer_version"],
        saved_count=result["saved_count"],
        conflicts=[AnswerConflictItem(**c) for c in result["conflicts"]],
    ))


@router.post("/{attempt_id}/submit", response_model=APIResponse[ExamResultResponse])
def submit_exam(attempt_id: int, data: ExamSubmitRequest, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """交卷。幂等：重复提交（网络重试/多端重复点击/与超时自动交卷并发）
    不会重复计分、占用考试次数或发证，统一返回首次评分结果（already=True）。
    """
    attempt = attempt_service.get_attempt(db, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="考试记录不存在")
    if attempt.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作他人的考试记录")

    # 已交卷（含被后台任务/其它端自动交卷）：直接幂等返回已有成绩
    if attempt.status == "graded":
        exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
        return APIResponse(data=_build_result(db, attempt, exam, already=True))

    # 答题用时异常检测（仅手动交卷、携带答案时）
    if data.submit_type != "timeout":
        for a in data.answers:
            if anti_cheat_service.validate_answer_time(db, attempt, a.question_id,
                                                       a.time_spent_seconds):
                attempt.cheat_warning_count += 1

    try:
        attempt = attempt_service.submit_exam(db, attempt, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
    # finalize 抢占成功（真正评分）标记为首次；并发下被其它请求抢先评分则 already=True
    already = not getattr(attempt, "_just_finalized", False)
    return APIResponse(data=_build_result(db, attempt, exam, already=already))


@router.get("/{attempt_id}/result", response_model=APIResponse[ExamResultResponse])
def get_result(attempt_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """获取交卷结果（刷新结果页 / 自动交卷后查询）。"""
    attempt = attempt_service.get_attempt(db, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="考试记录不存在")
    if attempt.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作他人的考试记录")
    if attempt.status != "graded":
        raise HTTPException(status_code=400, detail="考试尚未交卷")
    exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
    return APIResponse(data=_build_result(db, attempt, exam))


@router.post("/{attempt_id}/screen-switch", response_model=APIResponse[dict])
def screen_switch(attempt_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """前端在检测到用户切屏时上报一次"""
    attempt = attempt_service.get_attempt(db, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="考试记录不存在")
    if attempt.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作他人的考试记录")
    if attempt.status != "in_progress":
        return APIResponse(data={"warning": attempt.cheat_warning_count, "force_submit": False})

    force_submit = anti_cheat_service.record_screen_switch(db, attempt)
    # 达到阈值时仅通知客户端强制交卷：由客户端先保存最终答案再调 submit。
    # 若客户端未能提交（断网/关页），到时仍由后台任务按已保存答案自动交卷。
    return APIResponse(data={
        "warning": attempt.cheat_warning_count,
        "force_submit": force_submit,
    })
