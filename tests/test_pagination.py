"""
分页测试。
正确行为：page=1 应返回前 page_size 条数据（offset = (page-1) * page_size）。
"""
from app.services import question_service
from app.schemas.question import QuestionCreate, QuestionOptionCreate


def _seed_questions(db, n=15):
    qs = []
    for i in range(n):
        qs.append(question_service.create_question(db, QuestionCreate(
            question_type="single_choice",
            content=f"分页测试题目第 {i} 号",
            difficulty=3,
            knowledge_point_id=1,
            subject_id=1,
            options=[QuestionOptionCreate(content="A", is_correct=1, order_index=0),
                     QuestionOptionCreate(content="B", is_correct=0, order_index=1)],
        ), user_id=1))
    return qs


def test_first_page_returns_first_items(db):
    questions = _seed_questions(db, 15)
    total, items = question_service.list_questions(db, page=1, page_size=10)
    assert total == 15
    assert len(items) == 10, f"第一页应返回 10 条，实际 {len(items)}"
    assert items[0].id == questions[0].id, "第一页应从第一条开始，不应当跳过首页数据"


def test_second_page_returns_remaining(db):
    _seed_questions(db, 15)
    total, items = question_service.list_questions(db, page=2, page_size=10)
    assert len(items) == 5, f"第二页应返回剩余 5 条，实际 {len(items)}"
