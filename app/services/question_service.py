from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import (
    Subject, KnowledgePoint, Tag, Question, QuestionOption, QuestionTag,
)
from app.schemas.question import (
    SubjectCreate, KnowledgePointCreate, TagCreate,
    QuestionCreate, QuestionUpdate,
)


# ---------- 科目 ----------
def create_subject(db: Session, data: SubjectCreate) -> Subject:
    subject = Subject(name=data.name, code=data.code, description=data.description)
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return subject


def list_subjects(db: Session) -> list[Subject]:
    return db.query(Subject).all()


# ---------- 知识点 ----------
def create_knowledge_point(db: Session, data: KnowledgePointCreate) -> KnowledgePoint:
    kp = KnowledgePoint(
        name=data.name, parent_id=data.parent_id,
        subject_id=data.subject_id, description=data.description,
    )
    db.add(kp)
    db.commit()
    db.refresh(kp)
    return kp


def get_knowledge_point_tree(db: Session, subject_id: int) -> list[KnowledgePoint]:
    """返回指定科目下的知识点，按树形组织（children 已挂载）"""
    all_kp = db.query(KnowledgePoint).filter(
        KnowledgePoint.subject_id == subject_id
    ).all()
    kp_map = {kp.id: kp for kp in all_kp}
    roots = []
    for kp in all_kp:
        if kp.parent_id and kp.parent_id in kp_map:
            parent = kp_map[kp.parent_id]
            if not hasattr(parent, "children"):
                parent.children = []
            parent.children.append(kp)
        else:
            roots.append(kp)
    return roots


def list_knowledge_points(db: Session, subject_id: int | None = None) -> list[KnowledgePoint]:
    query = db.query(KnowledgePoint)
    if subject_id:
        query = query.filter(KnowledgePoint.subject_id == subject_id)
    return query.all()


# ---------- 标签 ----------
def create_tag(db: Session, data: TagCreate) -> Tag:
    tag = Tag(name=data.name, color=data.color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


def list_tags(db: Session) -> list[Tag]:
    return db.query(Tag).all()


# ---------- 题目 ----------
def create_question(db: Session, data: QuestionCreate, user_id: int) -> Question:
    question = Question(
        question_type=data.question_type,
        content=data.content,
        analysis=data.analysis,
        difficulty=data.difficulty,
        knowledge_point_id=data.knowledge_point_id,
        subject_id=data.subject_id,
        created_by=user_id,
    )
    db.add(question)
    db.flush()

    for opt in data.options:
        db.add(QuestionOption(
            question_id=question.id,
            content=opt.content,
            is_correct=opt.is_correct,
            order_index=opt.order_index,
        ))
    for tag_id in data.tag_ids:
        db.add(QuestionTag(question_id=question.id, tag_id=tag_id))

    db.commit()
    db.refresh(question)
    return question


def get_question(db: Session, question_id: int) -> Question | None:
    return db.query(Question).filter(Question.id == question_id).first()


def update_question(db: Session, question: Question, data: QuestionUpdate) -> Question:
    if data.question_type is not None:
        question.question_type = data.question_type
    if data.content is not None:
        question.content = data.content
    if data.analysis is not None:
        question.analysis = data.analysis
    if data.difficulty is not None:
        question.difficulty = data.difficulty
    if data.knowledge_point_id is not None:
        question.knowledge_point_id = data.knowledge_point_id

    if data.options is not None:
        question.options.clear()
        for opt in data.options:
            question.options.append(QuestionOption(
                content=opt.content,
                is_correct=opt.is_correct,
                order_index=opt.order_index,
            ))
    if data.tag_ids is not None:
        question.tags.clear()
        for tag_id in data.tag_ids:
            db.add(QuestionTag(question_id=question.id, tag_id=tag_id))

    db.commit()
    db.refresh(question)
    return question


def list_questions(db: Session, page: int = 1, page_size: int = 10,
                   question_type: str | None = None, difficulty: int | None = None,
                   knowledge_point_id: int | None = None,
                   subject_id: int | None = None,
                   keyword: str | None = None):
    query = db.query(Question)
    if question_type:
        query = query.filter(Question.question_type == question_type)
    if difficulty:
        query = query.filter(Question.difficulty == difficulty)
    if knowledge_point_id:
        query = query.filter(Question.knowledge_point_id == knowledge_point_id)
    if subject_id:
        query = query.filter(Question.subject_id == subject_id)
    if keyword:
        query = query.filter(Question.content.contains(keyword))

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return total, items


def delete_question(db: Session, question: Question) -> None:
    db.delete(question)
    db.commit()


def batch_import_questions(db: Session, questions: list[QuestionCreate], user_id: int) -> int:
    count = 0
    for data in questions:
        create_question(db, data, user_id)
        count += 1
    return count
