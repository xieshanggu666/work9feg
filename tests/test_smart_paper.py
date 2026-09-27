"""
智能组卷测试。
正确行为：组卷时每个参与权重的知识点都应分配到至少 1 题，
不能出现某个知识点"无题可抽"却静默跳过的情况。
"""
from app.models import Subject, KnowledgePoint, Question, QuestionOption
from app.schemas.exam import (
    SmartPaperGenRequest, KnowledgePointWeight,
    DifficultyDistribution, QuestionTypeDistribution,
)
from app.services import exam_service


def _seed(db):
    subject = Subject(name="组卷测试科目", code="PAPER", description="")
    db.add(subject)
    db.commit()
    db.refresh(subject)

    kps = {}
    for name in ["知识点A", "知识点B", "知识点C"]:
        kp = KnowledgePoint(name=name, subject_id=subject.id)
        db.add(kp)
        db.flush()
        kps[name] = kp.id

    # 每个知识点下放 8 道单选题（难度 2）
    for kp_id in kps.values():
        for i in range(8):
            q = Question(question_type="single_choice", content=f"组卷题-{kp_id}-{i}",
                         difficulty=2, knowledge_point_id=kp_id,
                         subject_id=subject.id, created_by=1)
            db.add(q)
            db.flush()
            db.add(QuestionOption(question_id=q.id, content="A", is_correct=1, order_index=0))
            db.add(QuestionOption(question_id=q.id, content="B", is_correct=0, order_index=1))
    db.commit()
    return subject.id, kps


def test_smart_paper_covers_all_knowledge_points(db):
    """权重极不均衡时（98%/1%/1%），每个知识点仍应覆盖至少 1 题"""
    subject_id, kps = _seed(db)

    req = SmartPaperGenRequest(
        title="覆盖性测试卷",
        subject_id=subject_id,
        total_score=100,
        duration_minutes=60,
        knowledge_point_weights=[
            KnowledgePointWeight(kp_id=kps["知识点A"], weight=98),
            KnowledgePointWeight(kp_id=kps["知识点B"], weight=1),
            KnowledgePointWeight(kp_id=kps["知识点C"], weight=1),
        ],
        difficulty_distribution=[DifficultyDistribution(level=2, percentage=100)],
        question_type_distribution=[
            QuestionTypeDistribution(question_type="single_choice", count=20),
        ],
    )

    paper, qids, actual_score, warnings = exam_service.smart_generate_paper(db, req, user_id=1)

    # 每个知识点都必须有题
    kp_covered = set()
    for qid in qids:
        q = db.query(Question).filter(Question.id == qid).first()
        kp_covered.add(q.knowledge_point_id)
    missing = set(kps.values()) - kp_covered
    assert not missing, f"以下知识点未覆盖到任何题目: {missing}"
