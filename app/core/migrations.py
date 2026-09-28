"""轻量级启动迁移：为已有 SQLite 数据库补齐新列（项目未引入 Alembic）。

只处理"新增可空/有默认值列"以及"新增唯一索引"这种向后兼容的场景；幂等。
"""
from sqlalchemy import inspect, text

from app.core.database import engine

# 表名 -> [(列名, 列定义 SQL), ...]
_NEW_COLUMNS = {
    "exam_attempts": [
        ("submit_type", "VARCHAR(20) DEFAULT ''"),
        ("answer_version", "INTEGER DEFAULT 0"),
        ("last_save_time", "DATETIME"),
    ],
    "exam_answers": [
        ("version", "INTEGER DEFAULT 0"),
        ("updated_at", "DATETIME"),
    ],
}

# 唯一索引名 -> 建索引 SQL
_NEW_INDEXES = {
    "uq_answer_attempt_question": (
        "CREATE UNIQUE INDEX uq_answer_attempt_question "
        "ON exam_answers (attempt_id, question_id)"
    ),
}


def run_migrations() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in _NEW_COLUMNS.items():
            if table not in existing_tables:
                continue  # 新库由 Base.metadata.create_all 建表
            present = {col["name"] for col in inspector.get_columns(table)}
            for name, ddl in columns:
                if name not in present:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))

        if "exam_answers" in existing_tables:
            present_indexes = set(inspector.get_indexes("exam_answers"))
            present_names = {ix["name"] for ix in present_indexes}
            for name, ddl in _NEW_INDEXES.items():
                if name not in present_names:
                    try:
                        conn.execute(text(ddl))
                    except Exception:
                        # 存量脏数据（重复草稿）时跳过，不阻断启动
                        pass
