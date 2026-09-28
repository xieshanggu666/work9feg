"""后台服务：到时自动交卷扫描。

不依赖任何前端在线——考试截止后由服务端按已自动保存的答案交卷评分。
单线程扫描即可，评分入口 ``grade_attempt`` 内部带每-attempt 锁且幂等，
与前端主动交卷、多实例（多 worker 时）并发安全。
"""
import threading
from datetime import datetime

from app.core.database import SessionLocal
from app.services import attempt_service

_sweeper_thread: threading.Thread | None = None
_stop_event = threading.Event()


def _run(interval_seconds: float) -> None:
    # 启动即扫一次（覆盖服务重启期间已到时的考试），之后周期扫描
    while not _stop_event.is_set():
        try:
            db = SessionLocal()
            try:
                attempt_service.auto_submit_due_attempts(db)
            finally:
                db.close()
        except Exception:  # noqa: BLE001 后台线程不能因单次异常退出
            pass
        _stop_event.wait(interval_seconds)


def start(interval_seconds: float = 10.0) -> None:
    global _sweeper_thread
    if _sweeper_thread is not None and _sweeper_thread.is_alive():
        return
    _stop_event.clear()
    _sweeper_thread = threading.Thread(
        target=_run, args=(interval_seconds,), name="auto-submit-sweeper", daemon=True,
    )
    _sweeper_thread.start()


def stop() -> None:
    _stop_event.set()
