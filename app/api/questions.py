from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models import User
from app.schemas.question import (
    SubjectCreate, SubjectResponse, KnowledgePointCreate, KnowledgePointResponse,
    TagCreate, TagResponse, QuestionCreate, QuestionUpdate, QuestionResponse,
    QuestionBatchImport, QuestionListResponse,
)
from app.schemas.common import APIResponse, PageResponse
from app.services import question_service

router = APIRouter(prefix="/questions", tags=["题库管理"])


# ---------- 科目 ----------
@router.get("/subjects", response_model=APIResponse[list[SubjectResponse]])
def list_subjects(db: Session = Depends(get_db)):
    return APIResponse(data=[SubjectResponse.model_validate(s) for s in question_service.list_subjects(db)])


@router.post("/subjects", response_model=APIResponse[SubjectResponse])
def create_subject(data: SubjectCreate, db: Session = Depends(get_db),
                   user: User = Depends(require_roles("admin", "teacher"))):
    return APIResponse(data=SubjectResponse.model_validate(question_service.create_subject(db, data)))


# ---------- 知识点 ----------
@router.get("/knowledge-points", response_model=APIResponse[list[KnowledgePointResponse]])
def list_knowledge_points(subject_id: int | None = None, db: Session = Depends(get_db)):
    kps = question_service.list_knowledge_points(db, subject_id)
    return APIResponse(data=[KnowledgePointResponse.model_validate(kp) for kp in kps])


@router.get("/knowledge-points/tree", response_model=APIResponse[list[KnowledgePointResponse]])
def knowledge_point_tree(subject_id: int, db: Session = Depends(get_db)):
    roots = question_service.get_knowledge_point_tree(db, subject_id)
    return APIResponse(data=[KnowledgePointResponse.model_validate(r) for r in roots])


@router.post("/knowledge-points", response_model=APIResponse[KnowledgePointResponse])
def create_knowledge_point(data: KnowledgePointCreate, db: Session = Depends(get_db),
                           user: User = Depends(require_roles("admin", "teacher"))):
    return APIResponse(data=KnowledgePointResponse.model_validate(
        question_service.create_knowledge_point(db, data)))


# ---------- 标签 ----------
@router.get("/tags", response_model=APIResponse[list[TagResponse]])
def list_tags(db: Session = Depends(get_db)):
    return APIResponse(data=[TagResponse.model_validate(t) for t in question_service.list_tags(db)])


@router.post("/tags", response_model=APIResponse[TagResponse])
def create_tag(data: TagCreate, db: Session = Depends(get_db),
               user: User = Depends(require_roles("admin", "teacher"))):
    return APIResponse(data=TagResponse.model_validate(question_service.create_tag(db, data)))


# ---------- 题目 ----------
@router.get("", response_model=APIResponse[PageResponse[QuestionListResponse]])
def list_questions(page: int = 1, page_size: int = 10,
                   question_type: str | None = None, difficulty: int | None = None,
                   knowledge_point_id: int | None = None,
                   subject_id: int | None = None, keyword: str | None = None,
                   db: Session = Depends(get_db)):
    total, items = question_service.list_questions(
        db, page, page_size, question_type, difficulty,
        knowledge_point_id, subject_id, keyword,
    )
    return APIResponse(data=PageResponse(
        total=total, page=page, page_size=page_size,
        items=[QuestionListResponse.model_validate(q) for q in items],
    ))


@router.post("", response_model=APIResponse[QuestionResponse])
def create_question(data: QuestionCreate, db: Session = Depends(get_db),
                    user: User = Depends(require_roles("admin", "teacher"))):
    q = question_service.create_question(db, data, user.id)
    return APIResponse(data=QuestionResponse.model_validate(q))


@router.post("/batch-import", response_model=APIResponse[dict])
def batch_import(data: QuestionBatchImport, db: Session = Depends(get_db),
                 user: User = Depends(require_roles("admin", "teacher"))):
    count = question_service.batch_import_questions(db, data.questions, user.id)
    return APIResponse(data={"imported": count})


@router.get("/{question_id}", response_model=APIResponse[QuestionResponse])
def get_question(question_id: int, db: Session = Depends(get_db)):
    q = question_service.get_question(db, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    return APIResponse(data=QuestionResponse.model_validate(q))


@router.put("/{question_id}", response_model=APIResponse[QuestionResponse])
def update_question(question_id: int, data: QuestionUpdate, db: Session = Depends(get_db),
                    user: User = Depends(require_roles("admin", "teacher"))):
    q = question_service.get_question(db, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    updated = question_service.update_question(db, q, data)
    return APIResponse(data=QuestionResponse.model_validate(updated))


@router.delete("/{question_id}", response_model=APIResponse)
def delete_question(question_id: int, db: Session = Depends(get_db),
                    user: User = Depends(require_roles("admin", "teacher"))):
    q = question_service.get_question(db, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    question_service.delete_question(db, q)
    return APIResponse(data=None)
