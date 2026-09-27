"""初始化数据库并写入示例数据。用法: python scripts/init_db.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import Base, engine, SessionLocal
from app.models import (
    User, Subject, KnowledgePoint, Tag,
)
from app.services import user_service, question_service, exam_service
from app.schemas.user import UserCreate
from app.schemas.question import SubjectCreate, KnowledgePointCreate, QuestionCreate, QuestionOptionCreate
from app.schemas.exam import ExamCreate


def main():
    print("重置数据库...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    # 1. 用户
    print("创建用户...")
    admin = user_service.create_user(db, UserCreate(
        username="admin", email="admin@exam.com", password="123456",
        real_name="系统管理员", role="admin"))
    teacher = user_service.create_user(db, UserCreate(
        username="teacher", email="teacher@exam.com", password="123456",
        real_name="王老师", role="teacher"))
    s1 = user_service.create_user(db, UserCreate(
        username="student1", email="s1@exam.com", password="123456",
        real_name="小明", role="student"))
    s2 = user_service.create_user(db, UserCreate(
        username="student2", email="s2@exam.com", password="123456",
        real_name="小红", role="student"))

    # 2. 科目
    print("创建科目与知识点...")
    py = question_service.create_subject(db, SubjectCreate(
        name="编程基础", code="PY101", description="Python 编程基础"))
    db.add(Tag(name="语法", color="#e74c3c"))
    db.add(Tag(name="数据结构", color="#3498db"))
    db.add(Tag(name="进阶", color="#9b59b6"))
    db.commit()

    kp_root = question_service.create_knowledge_point(db, KnowledgePointCreate(
        name="Python 基础", subject_id=py.id))
    kp_var = question_service.create_knowledge_point(db, KnowledgePointCreate(
        name="变量与数据类型", parent_id=kp_root.id, subject_id=py.id))
    kp_flow = question_service.create_knowledge_point(db, KnowledgePointCreate(
        name="流程控制", parent_id=kp_root.id, subject_id=py.id))
    kp_str = question_service.create_knowledge_point(db, KnowledgePointCreate(
        name="字符串处理", parent_id=kp_root.id, subject_id=py.id))
    kp_list = question_service.create_knowledge_point(db, KnowledgePointCreate(
        name="列表与字典", parent_id=kp_root.id, subject_id=py.id))
    kp_func = question_service.create_knowledge_point(db, KnowledgePointCreate(
        name="函数与模块", parent_id=kp_root.id, subject_id=py.id))

    # 3. 题目
    print("创建题库（24 题）...")
    Q = QuestionCreate
    Opt = QuestionOptionCreate
    qs = []

    # ---- 单选题 (难度 1~4) ----
    qs.append(Q(question_type="single_choice", difficulty=1,
                knowledge_point_id=kp_var.id, subject_id=py.id,
                content="Python 中表示整数的关键字是？",
                analysis="int 用于表示整数类型。",
                options=[Opt(content="int", is_correct=1, order_index=0),
                         Opt(content="float", is_correct=0, order_index=1),
                         Opt(content="str", is_correct=0, order_index=2),
                         Opt(content="bool", is_correct=0, order_index=3)]))
    qs.append(Q(question_type="single_choice", difficulty=1,
                knowledge_point_id=kp_var.id, subject_id=py.id,
                content="下列哪个不是 Python 的合法变量名？",
                analysis="变量名不能以数字开头。",
                options=[Opt(content="my_var", is_correct=0, order_index=0),
                         Opt(content="_value", is_correct=0, order_index=1),
                         Opt(content="1var", is_correct=1, order_index=2),
                         Opt(content="var1", is_correct=0, order_index=3)]))
    qs.append(Q(question_type="single_choice", difficulty=2,
                knowledge_point_id=kp_flow.id, subject_id=py.id,
                content="执行 x = 5; if x > 3: print('A') else: print('B') 的结果是？",
                analysis="5 > 3 成立，输出 A。",
                options=[Opt(content="A", is_correct=1, order_index=0),
                         Opt(content="B", is_correct=0, order_index=1),
                         Opt(content="AB", is_correct=0, order_index=2),
                         Opt(content="无输出", is_correct=0, order_index=3)]))
    qs.append(Q(question_type="single_choice", difficulty=2,
                knowledge_point_id=kp_list.id, subject_id=py.id,
                content="[1, 2, 3][-1] 的值是？",
                analysis="负索引从末尾取值，-1 表示最后一个元素。",
                options=[Opt(content="1", is_correct=0, order_index=0),
                         Opt(content="2", is_correct=0, order_index=1),
                         Opt(content="3", is_correct=1, order_index=2),
                         Opt(content="IndexError", is_correct=0, order_index=3)]))
    qs.append(Q(question_type="single_choice", difficulty=3,
                knowledge_point_id=kp_func.id, subject_id=py.id,
                content="关于 Python 函数默认参数，下列说法正确的是？",
                analysis="默认参数必须在非默认参数之后定义。",
                options=[Opt(content="默认参数可以放在任意位置", is_correct=0, order_index=0),
                         Opt(content="默认参数必须放在非默认参数之后", is_correct=1, order_index=1),
                         Opt(content="默认参数在调用时必须显式传入", is_correct=0, order_index=2),
                         Opt(content="默认参数只能是数字", is_correct=0, order_index=3)]))
    qs.append(Q(question_type="single_choice", difficulty=4,
                knowledge_point_id=kp_list.id, subject_id=py.id,
                content="d = {'a': 1, 'b': 2}; d.get('c', 3) 的返回值是？",
                analysis="get 在键不存在时返回默认值 3。",
                options=[Opt(content="None", is_correct=0, order_index=0),
                         Opt(content="KeyError", is_correct=0, order_index=1),
                         Opt(content="3", is_correct=1, order_index=2),
                         Opt(content="{}", is_correct=0, order_index=3)]))

    # ---- 多选题 (难度 2~4) ----
    qs.append(Q(question_type="multiple_choice", difficulty=2,
                knowledge_point_id=kp_var.id, subject_id=py.id,
                content="下列属于 Python 内置数据类型的有？",
                analysis="int、list、dict 均为内置类型；custom 不是。",
                options=[Opt(content="int", is_correct=1, order_index=0),
                         Opt(content="list", is_correct=1, order_index=1),
                         Opt(content="dict", is_correct=1, order_index=2),
                         Opt(content="custom", is_correct=0, order_index=3)]))
    qs.append(Q(question_type="multiple_choice", difficulty=3,
                knowledge_point_id=kp_str.id, subject_id=py.id,
                content="关于字符串 'hello'，下列说法正确的有？",
                analysis="字符串支持索引、切片、len()；字符串不可变。",
                options=[Opt(content="'hello'[0] == 'h'", is_correct=1, order_index=0),
                         Opt(content="'hello'[1:3] == 'el'", is_correct=1, order_index=1),
                         Opt(content="len('hello') == 5", is_correct=1, order_index=2),
                         Opt(content="'hello'[0] = 'H' 可以原地修改", is_correct=0, order_index=3)]))
    qs.append(Q(question_type="multiple_choice", difficulty=3,
                knowledge_point_id=kp_flow.id, subject_id=py.id,
                content="以下哪些写法可以正确遍历 0 到 9？",
                analysis="range(10)、list(range(10)) 遍历元素、for i in [0..9] 也可以，但 range(1,10) 少 0。",
                options=[Opt(content="for i in range(10)", is_correct=1, order_index=0),
                         Opt(content="for i in range(1, 10)", is_correct=0, order_index=1),
                         Opt(content="for i in list(range(10))", is_correct=1, order_index=2),
                         Opt(content="for i in [0,1,2,3,4,5,6,7,8,9]", is_correct=1, order_index=3)]))
    qs.append(Q(question_type="multiple_choice", difficulty=4,
                knowledge_point_id=kp_func.id, subject_id=py.id,
                content="关于装饰器，下列说法正确的有？",
                analysis="装饰器是接受函数并返回函数的可调用对象，可用来增强函数功能。",
                options=[Opt(content="装饰器本质是函数包装", is_correct=1, order_index=0),
                         Opt(content="@deco 等价于 f = deco(f)", is_correct=1, order_index=1),
                         Opt(content="装饰器只能用于函数不能用于类", is_correct=0, order_index=2),
                         Opt(content="装饰器可以叠加使用", is_correct=1, order_index=3)]))

    # ---- 判断题 (难度 1~3) ----
    qs.append(Q(question_type="judgment", difficulty=1,
                knowledge_point_id=kp_var.id, subject_id=py.id,
                content="Python 3 中 print 是函数而非语句。",
                analysis="正确|对",
                options=[Opt(content="正确", is_correct=1, order_index=0),
                         Opt(content="错误", is_correct=0, order_index=1)]))
    qs.append(Q(question_type="judgment", difficulty=1,
                knowledge_point_id=kp_var.id, subject_id=py.id,
                content="Python 中 0.1 + 0.2 == 0.3 恒为 True。",
                analysis="错误|错|False",
                options=[Opt(content="正确", is_correct=0, order_index=0),
                         Opt(content="错误", is_correct=1, order_index=1)]))
    qs.append(Q(question_type="judgment", difficulty=2,
                knowledge_point_id=kp_list.id, subject_id=py.id,
                content="列表 list 与元组 tuple 都可以修改元素。",
                analysis="错误|错",
                options=[Opt(content="正确", is_correct=0, order_index=0),
                         Opt(content="错误", is_correct=1, order_index=1)]))
    qs.append(Q(question_type="judgment", difficulty=2,
                knowledge_point_id=kp_flow.id, subject_id=py.id,
                content="while 循环可以使用 break 语句提前退出。",
                analysis="正确|对",
                options=[Opt(content="正确", is_correct=1, order_index=0),
                         Opt(content="错误", is_correct=0, order_index=1)]))
    qs.append(Q(question_type="judgment", difficulty=3,
                knowledge_point_id=kp_func.id, subject_id=py.id,
                content="Python 的 lambda 表达式可以包含多行语句。",
                analysis="错误|错",
                options=[Opt(content="正确", is_correct=0, order_index=0),
                         Opt(content="错误", is_correct=1, order_index=1)]))

    # ---- 填空题 (难度 2~4) ----
    qs.append(Q(question_type="fill_blank", difficulty=2,
                knowledge_point_id=kp_var.id, subject_id=py.id,
                content="Python 中获取字符串长度的内置函数是 ____。",
                analysis="len|len()"))
    qs.append(Q(question_type="fill_blank", difficulty=3,
                knowledge_point_id=kp_list.id, subject_id=py.id,
                content="在列表末尾添加元素的两种方法是 append 和 ____。",
                analysis="extend"))
    qs.append(Q(question_type="fill_blank", difficulty=3,
                knowledge_point_id=kp_str.id, subject_id=py.id,
                content="字符串 'abc' 的大写形式是 ____。",
                analysis="ABC"))
    qs.append(Q(question_type="fill_blank", difficulty=4,
                knowledge_point_id=kp_func.id, subject_id=py.id,
                content="定义函数使用的关键字是 ____，生成器函数返回 ____ 类型对象。",
                analysis="def|生成器|generator"))

    # ---- 简答题 (难度 4~5) ----
    qs.append(Q(question_type="short_answer", difficulty=4,
                knowledge_point_id=kp_var.id, subject_id=py.id,
                content="简述 Python 中深拷贝与浅拷贝的区别。",
                analysis="浅拷贝|引用|深拷贝|新对象|独立|内存"))
    qs.append(Q(question_type="short_answer", difficulty=5,
                knowledge_point_id=kp_list.id, subject_id=py.id,
                content="如何判断一个字符串是否为回文？请说明思路。",
                analysis="反转|比较|切片|[::-1]|指针|双指针"))

    # ---- 编程题 (难度 5) ----
    qs.append(Q(question_type="programming", difficulty=5,
                knowledge_point_id=kp_func.id, subject_id=py.id,
                content="编写函数 is_palindrome(s)，判断字符串 s 是否为回文串（忽略大小写与空格）。",
                analysis="翻转|比较|预处理|lower|replace"))
    qs.append(Q(question_type="programming", difficulty=5,
                knowledge_point_id=kp_list.id, subject_id=py.id,
                content="给定整数列表 nums，编写函数 two_sum(nums, target) 返回和为 target 的两个数的下标。",
                analysis="哈希|字典|遍历|互补"))

    saved = []
    for q in qs:
        saved.append(question_service.create_question(db, q, teacher.id))
    print(f"  已创建 {len(saved)} 道题目")

    # 4. 考试
    print("创建考试并组卷...")
    from datetime import datetime, timedelta
    from app.schemas.booking import SlotCreate
    from app.services import booking_service

    exam = exam_service.create_exam(db, ExamCreate(
        title="Python 基础水平测试",
        description="考察 Python 基础语法、数据结构与函数（需预约，允许 1 次补考）",
        subject_id=py.id,
        exam_type="formal",
        duration_minutes=60,
        total_score=100,
        pass_score=60,
        anti_cheat_enabled=1,
        require_booking=1,
        max_attempts=2,
    ), teacher.id)
    # 选取 10 题，每题 10 分
    for idx, q in enumerate(saved[:10]):
        exam_service.add_question_to_exam(db, exam, q.id, score=10, order_index=idx)
    exam.status = "published"
    db.commit()
    db.refresh(exam)
    print(f"  考试 #{exam.id} 已发布，包含 {len(exam.questions)} 题")

    # 5. 预约时段与示例预约
    print("配置考试时段并生成示例预约...")
    now = datetime.now()
    slot1 = booking_service.create_slot(db, exam.id, SlotCreate(
        name="第一批次（本周）",
        start_time=now - timedelta(days=1),
        end_time=now + timedelta(days=6),
        capacity=30,
    ))
    slot2 = booking_service.create_slot(db, exam.id, SlotCreate(
        name="第二批次（下周）",
        start_time=now + timedelta(days=7),
        end_time=now + timedelta(days=14),
        capacity=20,
    ))
    # student1 首考预约已审核通过（可直接开考）
    b1 = booking_service.apply_booking(db, exam.id, slot1.id, s1.id, reason="正常参加首考")
    booking_service.review_booking(db, b1, teacher.id, True, "同意")
    # student2 提交了首考预约，等待教师审核
    booking_service.apply_booking(db, exam.id, slot2.id, s2.id, reason="申请第二批次首考")
    print(f"  已创建 2 个时段（名额 {slot1.capacity}/{slot2.capacity}）与 2 条示例预约")

    print("\n✅ 初始化完成！")
    print("   管理员: admin / 123456")
    print("   教师:   teacher / 123456")
    print("   学生:   student1 / 123456（预约已通过，可直接开考）")
    print("           student2 / 123456（补考申请待审核）")
    print("   启动: uvicorn app.main:app --reload")


if __name__ == "__main__":
    main()
