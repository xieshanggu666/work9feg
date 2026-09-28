"""到时自动交卷后台任务。

周期性扫描进行中且已过截止时刻的考试，按服务端已保存的答案自动交卷，
保证学生关页面/断网/刷新后考试仍会按时收卷，不依赖客户端倒计时。
"""
import threading

from app.core.config import settings
from app.core.database import SessionLocal
from app.services import attempt_service


def run_sweep() -> int:
    """执行一次扫描（独立 DB 会话），供后台线程或外部调度器调用。"""
    db = SessionLocal()
    try:
        return attempt_service.auto_submit_due_attempts(db)
    finally:
        db.close()


def _loop(stop_event: threading.Event, interval: int) -> None:
    # 启动后先等一个间隔，避免与应用启动/建表竞争
    while not stop_event.wait(interval):
        try:
            run_sweep()
        except Exception:  # noqa: BLE001 后台任务不能因单次异常退出
            pass


def start_worker() -> tuple[threading.Thread, threading.Event]:
    interval = max(1, settings.AUTO_SUBMIT_INTERVAL_SECONDS)
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_loop, args=(stop_event, interval), name="auto-submit", daemon=True
    )
    thread.start()
    return thread, stop_event
