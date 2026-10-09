"""
服務生命週期迴圈：每分鐘判斷是否在啟用窗口內，進入窗口就開始一次 session，
窗口結束後收尾並回到待機，下個時段重新開始（每個時段都是全新連線）。
"""
import threading
import traceback
from collections.abc import Callable

POLL_INTERVAL_SECONDS = 60.0

ShouldContinue = Callable[[], bool]


def _is_active_or_assume_active(name: str, is_active_fn: Callable[[], bool]) -> bool:
    """判斷失敗時保守視為啟用，避免因為判斷邏輯出錯而漏掉整個時段的資料"""
    try:
        return is_active_fn()
    except Exception as e:
        print(f"⚠️  [{name}] 判斷啟用時段失敗，保守視為啟用: {type(e).__name__}: {e}")
        return True


def run_session_loop(
    name: str,
    run_session: Callable[[ShouldContinue], None],
    is_active_fn: Callable[[], bool],
    stop_event: threading.Event,
    poll_interval: float = POLL_INTERVAL_SECONDS,
) -> None:
    """
    反覆執行 session 直到 stop_event 被設定。

    Args:
        name: 服務名稱，僅用於日誌
        run_session: 執行一個時段的工作並阻塞到結束；收到的 should_continue() 回傳 False 時
            （啟用窗口結束或服務要關閉）必須完成收尾後返回。拋出例外代表本次 session 失敗，
            會在下一輪（poll_interval 後）若仍在窗口內重新開始。
        is_active_fn: 目前是否在啟用窗口內
        stop_event: 設定後結束整個迴圈（例如收到 SIGTERM）
        poll_interval: 待機時檢查啟用窗口的間隔秒數
    """
    def should_continue() -> bool:
        return not stop_event.is_set() and _is_active_or_assume_active(name, is_active_fn)

    while not stop_event.is_set():
        if _is_active_or_assume_active(name, is_active_fn):
            print(f"▶️  [{name}] 進入啟用時段，開始執行")
            try:
                run_session(should_continue)
                print(f"⏹️  [{name}] 本時段已結束，回到待機")
            except Exception as e:
                print(f"❌ [{name}] 執行時發生錯誤，將於下一輪重試: {type(e).__name__}: {e}")
                traceback.print_exc()

        stop_event.wait(poll_interval)
