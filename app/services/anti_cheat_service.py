from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ExamAttempt, ExamAnswer


def record_screen_switch(db: Session, attempt: ExamAttempt) -> bool:
    """
    记录一次切屏，达到阈值时返回 True 触发警告。
    超过最大次数时由调用方强制交卷。
    """
    attempt.screen_switch_count += 1

    attempt.cheat_warning_count = attempt.screen_switch_count
    db.commit()

    if attempt.screen_switch_count >= settings.MAX_SCREEN_SWITCH_COUNT:
        return True
    return False


def validate_answer_time(db: Session, attempt: ExamAttempt, question_id: int,
                         time_spent_seconds: int) -> bool:
    """
    答题用时校验：单题用时低于最小阈值视为作弊嫌疑。
    返回 True 表示用时异常。
    """
    if time_spent_seconds <= 0:
        return True
    if time_spent_seconds < settings.MIN_ANSWER_SECONDS:
        # 记录警告
        attempt.cheat_warning_count = attempt.cheat_warning_count + 1
        db.commit()
        return True
    return False


def check_ip_duplicate(db: Session, exam_id: int, ip: str, user_id: int) -> int:
    """检测同一 IP 下有多个不同用户参加同一考试"""
    others = (
        db.query(ExamAttempt)
        .filter(
            ExamAttempt.exam_id == exam_id,
            ExamAttempt.ip_address == ip,
            ExamAttempt.user_id != user_id,
        )
        .count()
    )
    return others
