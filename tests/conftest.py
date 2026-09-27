import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
import app.models  # noqa: F401 注册模型


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def make_user(db):
    def _make(username="u", password="123456", role="student"):
        from app.services import user_service
        from app.schemas.user import UserCreate
        return user_service.create_user(db, UserCreate(
            username=username,
            email=f"{username}@test.com",
            password=password,
            real_name=username,
            role=role,
        ))
    return _make


@pytest.fixture
def make_question(db):
    def _make(qtype="single_choice", difficulty=3, correct_ids=(1,), options=None, analysis=""):
        from app.models import Question, QuestionOption
        q = Question(
            question_type=qtype,
            content=f"测试题目-{qtype}-{difficulty}",
            difficulty=difficulty,
            knowledge_point_id=1,
            subject_id=1,
            created_by=1,
            analysis=analysis,
        )
        db.add(q)
        db.flush()
        if options is None:
            options = [("A", i in correct_ids) for i in range(1, 5)]
        for i, (content, is_correct) in enumerate(options):
            db.add(QuestionOption(question_id=q.id, content=content,
                                  is_correct=1 if is_correct else 0, order_index=i))
        db.commit()
        db.refresh(q)
        return q
    return _make
