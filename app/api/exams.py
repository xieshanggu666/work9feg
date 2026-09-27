from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.models import User
from app.schemas.exam import (
    ExamCreate, ExamUpdate, ExamResponse, ExamDetailResponse,
    ExamQuestionAdd, PaperCreate, PaperResponse,
    SmartPaperGenRequest, SmartPaperGenResponse,
)
from app.schemas.common import APIResponse, PageResponse
from app.services import exam_service, question_service

router = APIRouter(prefix="/exams", tags=["考试管理"])


@router.get("", response_model=APIResponse[PageResponse[ExamResponse]])
def list_exams(page: int = 1, page_size: int = 10,
               status: str | None = None, subject_id: int | None = None,
               db: Session = Depends(get_db)):
    total, items = exam_service.list_exams(db, page, page_size, status, subject_id)
    return APIResponse(data=PageResponse(
        total=total, page=page, page_size=page_size,
        items=[ExamResponse.model_validate(e) for e in items],
    ))


@router.post("", response_model=APIResponse[ExamResponse])
def create_exam(data: ExamCreate, db: Session = Depends(get_db),
                user: User = Depends(require_roles("admin", "teacher"))):
    exam = exam_service.create_exam(db, data, user.id)
    return APIResponse(data=ExamResponse.model_validate(exam))


@router.get("/{exam_id}", response_model=APIResponse[ExamDetailResponse])
def get_exam(exam_id: int, db: Session = Depends(get_db)):
    exam = exam_service.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="考试不存在")
    data = ExamDetailResponse.model_validate(exam)
    data.question_count = len(exam.questions)
    return APIResponse(data=data)


@router.put("/{exam_id}", response_model=APIResponse[ExamResponse])
def update_exam(exam_id: int, data: ExamUpdate, db: Session = Depends(get_db),
                user: User = Depends(require_roles("admin", "teacher"))):
    exam = exam_service.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="考试不存在")
    updated = exam_service.update_exam(db, exam, data)
    return APIResponse(data=ExamResponse.model_validate(updated))


@router.delete("/{exam_id}", response_model=APIResponse)
def delete_exam(exam_id: int, db: Session = Depends(get_db),
                user: User = Depends(require_roles("admin", "teacher"))):
    exam = exam_service.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="考试不存在")
    exam_service.delete_exam(db, exam)
    return APIResponse(data=None)


@router.post("/{exam_id}/questions", response_model=APIResponse)
def add_question(exam_id: int, data: ExamQuestionAdd, db: Session = Depends(get_db),
                 user: User = Depends(require_roles("admin", "teacher"))):
    exam = exam_service.get_exam(db, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="考试不存在")
    question_service.get_question(db, data.question_id) or \
        (_ for _ in ()).throw(HTTPException(status_code=404, detail="题目不存在"))
    exam_service.add_question_to_exam(db, exam, data.question_id, data.score, data.order_index)
    return APIResponse(data=None)


@router.delete("/{exam_id}/questions/{exam_question_id}", response_model=APIResponse)
def remove_question(exam_id: int, exam_question_id: int, db: Session = Depends(get_db),
                    user: User = Depends(require_roles("admin", "teacher"))):
    exam_service.remove_question_from_exam(db, exam_question_id)
    return APIResponse(data=None)


# ---------- 试卷 ----------
@router.post("/papers", response_model=APIResponse[PaperResponse])
def create_paper(data: PaperCreate, db: Session = Depends(get_db),
                 user: User = Depends(require_roles("admin", "teacher"))):
    paper = exam_service.create_paper(db, data, user.id)
    return APIResponse(data=PaperResponse.model_validate(paper))


@router.post("/papers/smart-generate", response_model=APIResponse[SmartPaperGenResponse])
def smart_generate(data: SmartPaperGenRequest, db: Session = Depends(get_db),
                   user: User = Depends(require_roles("admin", "teacher"))):
    paper, qids, actual_score, warnings = exam_service.smart_generate_paper(db, data, user.id)
    return APIResponse(data=SmartPaperGenResponse(
        paper_id=paper.id, selected_questions=qids,
        actual_total_score=actual_score, warnings=warnings,
    ))
