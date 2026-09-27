"""
多选题评分测试。
正确行为：漏选给部分分，错选（选中错误选项）得 0 分。
"""
from app.schemas.attempt import AnswerSubmit
from app.services import attempt_service


def test_multiple_choice_full_correct(db, make_question):
    q = make_question("multiple_choice", correct_ids=(1, 2))
    correct, score = attempt_service._grade_answer(q, AnswerSubmit(
        question_id=q.id, user_answer="1,2"))
    assert correct is True
    assert score == 5.0


def test_multiple_choice_partial_credit(db, make_question):
    """漏选：只选对了 1 个，应得部分分"""
    q = make_question("multiple_choice", correct_ids=(1, 2))
    correct, score = attempt_service._grade_answer(q, AnswerSubmit(
        question_id=q.id, user_answer="1"))
    assert correct is False
    assert score == 2.5


def test_multiple_choice_wrong_option_zero(db, make_question):
    """错选：选中了错误选项 3，必须得 0 分（不能给部分分）"""
    q = make_question("multiple_choice", correct_ids=(1, 2))
    correct, score = attempt_service._grade_answer(q, AnswerSubmit(
        question_id=q.id, user_answer="1,3"))
    assert correct is False
    assert score == 0.0, f"错选不应得分，实际得分 {score}"


def test_multiple_choice_all_wrong(db, make_question):
    q = make_question("multiple_choice", correct_ids=(1, 2))
    correct, score = attempt_service._grade_answer(q, AnswerSubmit(
        question_id=q.id, user_answer="3,4"))
    assert score == 0.0
