from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User, Exam, ExamAttempt
from app.schemas.attempt import (
    ExamStartResponse, ExamQuestionBrief, SavedAnswer,
    ExamAutosaveRequest, ExamAutosaveResponse, SavedAnswerResult, ConflictItem,
    ExamSubmitRequest, ExamResultResponse, ExamAnswerResponse,
)
from app.schemas.common import APIResponse
from app.services import attempt_service, grade_service

router = APIRouter(prefix="/attempts", tags=["考试答题"])


def _build_session_payload(db: Session, attempt: ExamAttempt, exam: Exam) -> ExamStartResponse:
    """构造进入/恢复考试所需的全部数据：题目、已保存答案、服务端时钟、截止时刻。"""
    questions = attempt_service._collect_exam_questions(db, exam)
    drafts = attempt_service.get_draft_answers(db, attempt.id)
    now = datetime.now()
    return ExamStartResponse(
        attempt_id=attempt.id,
        exam_id=exam.id,
        title=exam.title,
        duration_minutes=exam.duration_minutes,
        total_score=exam.total_score,
        start_time=attempt.start_time,
        server_time=now,
        deadline=attempt_service.get_deadline(attempt, exam),
        status=attempt.status,
        questions=[ExamQuestionBrief(**q) for q in questions],
        answers=[
            SavedAnswer(
                question_id=d.question_id,
                user_answer=d.user_answer or "",
                time_spent_seconds=d.time_spent_seconds or 0,
                version=d.version,
            )
            for d in drafts
        ],
    )


@router.post("/{exam_id}/start", response_model=APIResponse[ExamStartResponse])
def start_exam(exam_id: int, request: Request, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """开始 / 恢复考试。

    刷新、重连或换端进入时：进行中的考试复用原 attempt 并回传已保存答案；
    已交卷的考试回传 status=graded（前端直接跳结果页），不会新建考试、
    不重复占用考试次数。
    """
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="考试不存在")
    if exam.status != "published":
        raise HTTPException(status_code=400, detail="考试未发布")

    client_ip = request.client.host if request.client else ""
    user_agent = request.headers.get("user-agent", "")
    try:
        attempt = attempt_service.start_exam(
            db, exam, user.id, client_ip, user_agent, resume=True
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return APIResponse(data=_build_session_payload(db, attempt, exam))


@router.get("/{attempt_id}/resume", response_model=APIResponse[ExamStartResponse])
def resume_exam(attempt_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """按 attempt_id 恢复（重连后不知道原 attempt 时由 start 接口兜底）。"""
    attempt = attempt_service.get_attempt(db, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="考试记录不存在")
    if attempt.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权查看他人的考试记录")
    exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="考试不存在")
    return APIResponse(data=_build_session_payload(db, attempt, exam))


@router.post("/{attempt_id}/autosave", response_model=APIResponse[ExamAutosaveResponse])
def autosave(attempt_id: int, data: ExamAutosaveRequest,
             db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """自动保存答案；返回每题最新版本（多端冲突检测）与考试状态。

    若考试刚好到时，服务端会先按已保存答案自动交卷，返回 status=graded。
    """
    attempt = attempt_service.get_attempt(db, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="考试记录不存在")
    if attempt.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作他人的考试记录")

    try:
        result = attempt_service.save_answers(db, attempt, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return APIResponse(data=ExamAutosaveResponse(
        attempt_id=result["attempt_id"],
        status=result["status"],
        server_time=result["server_time"],
        deadline=result["deadline"],
        saved=[SavedAnswerResult(**s) for s in result["saved"]],
        versions={str(k): v for k, v in result["versions"].items()},
        conflicts=[ConflictItem(**c) for c in result["conflicts"]],
    ))


def _build_result_response(db: Session, attempt: ExamAttempt) -> ExamResultResponse:
    exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
    answers = attempt_service.get_attempt_result(db, attempt)

    rank_info = None
    try:
        rank_info = grade_service.get_user_rank(
            db, attempt.user_id, attempt.exam_id, attempt_id=attempt.id
        )
    except ValueError:
        pass

    # 预约/补考联动：通过则自动发放证书（内部幂等）
    grade_service.auto_issue_certificate(db, attempt)

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
    )


@router.post("/{attempt_id}/submit", response_model=APIResponse[ExamResultResponse])
def submit_exam(attempt_id: int, data: ExamSubmitRequest, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """交卷。

    - 到时后仍允许调用：服务端只按已自动保存的答案评分（忽略迟到请求体）；
    - 重复请求（双击、前端重试、多端同时交卷、服务端自动交卷竞争）只评分一次，
      不重复计分、不重复占用考试次数、不重复发证；
    - 已交卷的请求直接返回同一结果。
    """
    attempt = attempt_service.get_attempt(db, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="考试记录不存在")
    if attempt.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作他人的考试记录")

    try:
        attempt = attempt_service.grade_attempt(db, attempt, data=data, late=False)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return APIResponse(data=_build_result_response(db, attempt))


@router.get("/{attempt_id}/result", response_model=APIResponse[ExamResultResponse])
def get_result(attempt_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """获取交卷结果（刷新结果页 / 自动交卷后轮询用）。未交卷返回 409。"""
    attempt = attempt_service.get_attempt(db, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="考试记录不存在")
    if attempt.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权查看他人的考试记录")
    if attempt.status != "graded":
        raise HTTPException(status_code=409, detail="考试尚未交卷")
    return APIResponse(data=_build_result_response(db, attempt))


@router.post("/{attempt_id}/screen-switch", response_model=APIResponse[dict])
def screen_switch(attempt_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """前端在检测到用户切屏时上报一次"""
    attempt = attempt_service.get_attempt(db, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="考试记录不存在")
    if attempt.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作他人的考试记录")

    from app.services import anti_cheat_service
    force_submit = anti_cheat_service.record_screen_switch(db, attempt)
    return APIResponse(data={
        "warning": attempt.cheat_warning_count,
        "force_submit": force_submit,
    })
