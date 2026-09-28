from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "在线考试与题库管理系统"
    API_PREFIX: str = "/api"
    SECRET_KEY: str = "exam-system-secret-key-please-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24小时

    # SQLite 数据库文件
    DATABASE_URL: str = "sqlite:///./data/exam_system.db"

    # 防作弊阈值
    SCREEN_SWITCH_LIMIT: int = 3          # 切屏超过该次数触发警告
    MAX_SCREEN_SWITCH_COUNT: int = 5      # 超过该次数强制交卷
    MIN_ANSWER_SECONDS: int = 5           # 单题最少用时，低于视为异常

    # 到时自动交卷：后台扫描间隔（秒）
    AUTO_SUBMIT_INTERVAL_SECONDS: int = 15
    # 前端自动保存答案的建议间隔（秒）
    ANSWER_AUTOSAVE_INTERVAL_SECONDS: int = 10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
