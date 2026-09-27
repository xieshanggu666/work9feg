from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Question, Exam, ExamQuestion, Paper, PaperQuestion,
)
from app.schemas.exam import (
    ExamCreate, ExamUpdate, PaperCreate, SmartPaperGenRequest,
)


# ---------- 考试 CRUD ----------
def create_exam(db: Session, data: ExamCreate, user_id: int) -> Exam:
    exam = Exam(**data.model_dump(), created_by=user_id)
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam


def get_exam(db: Session, exam_id: int) -> Exam | None:
    return db.query(Exam).filter(Exam.id == exam_id).first()


def list_exams(db: Session, page: int = 1, page_size: int = 10,
               status: str | None = None, subject_id: int | None = None):
    query = db.query(Exam)
    if status:
        query = query.filter(Exam.status == status)
    if subject_id:
        query = query.filter(Exam.subject_id == subject_id)
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return total, items


def update_exam(db: Session, exam: Exam, data: ExamUpdate) -> Exam:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(exam, field, value)
    db.commit()
    db.refresh(exam)
    return exam


def delete_exam(db: Session, exam: Exam) -> None:
    db.delete(exam)
    db.commit()


def add_question_to_exam(db: Session, exam: Exam, question_id: int,
                         score: int = 5, order_index: int = 0) -> ExamQuestion:
    eq = ExamQuestion(exam_id=exam.id, question_id=question_id,
                      score=score, order_index=order_index)
    db.add(eq)
    db.commit()
    db.refresh(eq)
    return eq


def remove_question_from_exam(db: Session, exam_question_id: int) -> None:
    eq = db.query(ExamQuestion).filter(ExamQuestion.id == exam_question_id).first()
    if eq:
        db.delete(eq)
        db.commit()


# ---------- 试卷 ----------
def create_paper(db: Session, data: PaperCreate, user_id: int) -> Paper:
    paper = Paper(
        title=data.title,
        description=data.description,
        subject_id=data.subject_id,
        total_score=data.total_score,
        created_by=user_id,
    )
    db.add(paper)
    db.flush()

    score_map = data.scores or {}
    for idx, qid in enumerate(data.question_ids):
        db.add(PaperQuestion(
            paper_id=paper.id, question_id=qid,
            score=score_map.get(qid, 5), order_index=idx,
        ))
    db.commit()
    db.refresh(paper)
    return paper


def get_paper(db: Session, paper_id: int) -> Paper | None:
    return db.query(Paper).filter(Paper.id == paper_id).first()


def _question_score(question: Question) -> int:
    """题目分值：难度越高分值越高"""
    return question.difficulty + 1


def smart_generate_paper(db: Session, req: SmartPaperGenRequest, user_id: int) -> tuple[Paper, list[int], int, list[str]]:
    """
    智能组卷算法：
    1. 根据题型分布确定总题数
    2. 按知识点权重把题目数量分配到各个知识点
    3. 每个知识点-题型组合内，按难度分布比例抽题
    4. 抽中的题目不重复，最后按题目难度计算实际总分
    """
    subject_id = req.subject_id
    total_questions = sum(t.count for t in req.question_type_distribution)
    if total_questions <= 0:
        raise ValueError("题型分布题目总数必须大于 0")

    weight_sum = sum(w.weight for w in req.knowledge_point_weights)
    if weight_sum <= 0:
        raise ValueError("知识点权重之和必须大于 0")

    difficulty_pool = {d.level: d.percentage for d in req.difficulty_distribution}
    if abs(sum(difficulty_pool.values()) - 100) > 0.01:
        raise ValueError("难度分布百分比之和必须为 100")

    kp_counts: dict[int, int] = {}
    allocated = 0
    for w in req.knowledge_point_weights[:-1]:
        cnt = int(total_questions * w.weight / weight_sum)
        kp_counts[w.kp_id] = cnt
        allocated += cnt
    kp_counts[req.knowledge_point_weights[-1].kp_id] = total_questions - allocated

    selected_qids: list[int] = []
    warnings: list[str] = []
    actual_score = 0

    for t in req.question_type_distribution:
        for kp_id, kp_cnt in kp_counts.items():
            # 该知识点下该题型的期望题数（按知识点占比折算）
            target = int(t.count * kp_cnt / total_questions)
            if target <= 0:
                continue
            # 按难度分布抽题
            for level, pct in sorted(difficulty_pool.items()):
                level_target = max(1, int(target * pct / 100))
                candidates = (
                    db.query(Question)
                    .filter(
                        Question.subject_id == subject_id,
                        Question.knowledge_point_id == kp_id,
                        Question.question_type == t.question_type,
                        Question.difficulty == level,
                    )
                    .order_by(func.random())
                    .limit(level_target)
                    .all()
                )
                for q in candidates:
                    if q.id in selected_qids:
                        continue
                    selected_qids.append(q.id)
                    actual_score += _question_score(q)

    if len(selected_qids) < total_questions:
        warnings.append(
            f"题库题目不足，实际抽取 {len(selected_qids)}/{total_questions} 题"
        )

    if not selected_qids:
        raise ValueError("未抽到任何符合条件的题目，请检查题库")

    paper = Paper(
        title=req.title,
        subject_id=subject_id,
        total_score=actual_score,
        created_by=user_id,
    )
    db.add(paper)
    db.flush()
    for idx, qid in enumerate(selected_qids):
        db.add(PaperQuestion(
            paper_id=paper.id, question_id=qid,
            score=_question_score(db.query(Question).filter(Question.id == qid).first()),
            order_index=idx,
        ))
    db.commit()
    db.refresh(paper)
    return paper, selected_qids, actual_score, warnings
