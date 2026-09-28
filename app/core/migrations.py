"""极简结构迁移（SQLite）。

项目使用 ``Base.metadata.create_all`` 建表，无法为已存在的表/约束执行增量变更。
这里用 PRAGMA 检查列、用表重建方式补唯一约束，保证旧版本数据库无需删库即可升级。
新数据库由 create_all 直接建好，迁移逻辑自动跳过。
"""
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.database import Base


def _table_columns(engine: Engine, table: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def _has_attempt_question_unique_index(engine: Engine) -> bool:
    """检查 exam_answers 是否已存在 (attempt_id, question_id) 唯一索引/约束。

    SQLite 中表级 UNIQUE 约束会生成 sqlite_autoindex_* 命名的自动索引，
    因此不能按约束名判断，需检查索引的 unique 标志与列。
    """
    with engine.connect() as conn:
        indexes = conn.execute(
            text("PRAGMA index_list('exam_answers')")
        ).fetchall()
        for idx in indexes:
            index_name = idx[1]
            is_unique = idx[2]
            if not is_unique:
                continue
            cols = conn.execute(text(f"PRAGMA index_info('{index_name}')")).fetchall()
            col_names = {row[2] for row in cols}
            if {"attempt_id", "question_id"} <= col_names:
                return True
    return False


def run_migrations(engine: Engine) -> None:
    # create_all 先补齐缺失的表
    Base.metadata.create_all(bind=engine)

    if engine.dialect.name != "sqlite":
        return

    cols = _table_columns(engine, "exam_answers")
    if not cols:
        return

    # 1) exam_answers.version 列
    if "version" not in cols:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE exam_answers ADD COLUMN version INTEGER NOT NULL DEFAULT 0"
            ))

    # 2) (attempt_id, question_id) 唯一约束：SQLite 需重建表。
    #    检查放在事务外，避免迁移期间另开连接读取造成锁竞争。
    if _has_attempt_question_unique_index(engine):
        return

    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.execute(text("""
            CREATE TABLE exam_answers_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attempt_id INTEGER NOT NULL REFERENCES exam_attempts(id),
                question_id INTEGER NOT NULL REFERENCES questions(id),
                user_answer TEXT DEFAULT '',
                is_correct INTEGER DEFAULT 0,
                score FLOAT DEFAULT 0.0,
                time_spent_seconds INTEGER DEFAULT 0,
                version INTEGER NOT NULL DEFAULT 0,
                CONSTRAINT ux_answers_attempt_question UNIQUE (attempt_id, question_id)
            )
        """))
        # 历史脏数据（同一 attempt+question 多条）合并为一条后再迁移
        conn.execute(text("""
            INSERT INTO exam_answers_new
                (id, attempt_id, question_id, user_answer, is_correct,
                 score, time_spent_seconds, version)
            SELECT MAX(id), attempt_id, question_id,
                   (SELECT user_answer FROM exam_answers ea2
                    WHERE ea2.attempt_id = ea.attempt_id
                      AND ea2.question_id = ea.question_id
                    ORDER BY ea2.id DESC LIMIT 1),
                   (SELECT is_correct FROM exam_answers ea2
                    WHERE ea2.attempt_id = ea.attempt_id
                      AND ea2.question_id = ea.question_id
                    ORDER BY ea2.id DESC LIMIT 1),
                   (SELECT score FROM exam_answers ea2
                    WHERE ea2.attempt_id = ea.attempt_id
                      AND ea2.question_id = ea.question_id
                    ORDER BY ea2.id DESC LIMIT 1),
                   MAX(time_spent_seconds), MAX(version)
            FROM exam_answers ea
            GROUP BY attempt_id, question_id
        """))
        # 旧表的同名索引在其被删除前仍占用名字，先用临时索引名，待表改名后重建
        conn.execute(text("""
            CREATE INDEX ix_exam_answers_new_attempt_id
            ON exam_answers_new (attempt_id)
        """))
        conn.execute(text("DROP TABLE exam_answers"))
        conn.execute(text("ALTER TABLE exam_answers_new RENAME TO exam_answers"))
        conn.execute(text("DROP INDEX ix_exam_answers_new_attempt_id"))
        conn.execute(text("""
            CREATE INDEX ix_exam_answers_attempt_id
            ON exam_answers (attempt_id)
        """))
        conn.execute(text("PRAGMA foreign_keys=ON"))
