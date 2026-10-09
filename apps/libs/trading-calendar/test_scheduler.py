"""
測試每分鐘判斷是否啟用的 session 生命週期迴圈
"""
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "src"))

from trading_calendar import ShouldContinue, run_session_loop


def test_runs_session_when_active_and_exits_when_stop_event_set() -> None:
    stop = threading.Event()
    seen: list[bool] = []

    def run_session(should_continue: ShouldContinue) -> None:
        seen.append(should_continue())
        stop.set()

    run_session_loop("test", run_session, lambda: True, stop, poll_interval=0)

    assert seen == [True]


def test_does_not_run_session_while_inactive() -> None:
    stop = threading.Event()
    checks = {"count": 0}

    def is_active() -> bool:
        checks["count"] += 1
        if checks["count"] >= 3:
            stop.set()
        return False

    def run_session(should_continue: ShouldContinue) -> None:
        pytest.fail("待機時段不應該啟動 session")

    run_session_loop("test", run_session, is_active, stop, poll_interval=0)

    assert checks["count"] == 3


def test_failed_session_is_retried_on_next_round(capsys: pytest.CaptureFixture[str]) -> None:
    stop = threading.Event()
    attempts: list[int] = []

    def run_session(should_continue: ShouldContinue) -> None:
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("boom")
        stop.set()

    run_session_loop("test", run_session, lambda: True, stop, poll_interval=0)

    assert len(attempts) == 2
    assert "RuntimeError: boom" in capsys.readouterr().out


def test_should_continue_turns_false_when_window_closes() -> None:
    stop = threading.Event()
    state = {"active": True}
    seen: list[bool] = []

    def run_session(should_continue: ShouldContinue) -> None:
        seen.append(should_continue())
        state["active"] = False
        seen.append(should_continue())
        stop.set()

    run_session_loop("test", run_session, lambda: state["active"], stop, poll_interval=0)

    assert seen == [True, False]


def test_should_continue_turns_false_when_stop_requested() -> None:
    stop = threading.Event()
    seen: list[bool] = []

    def run_session(should_continue: ShouldContinue) -> None:
        stop.set()
        seen.append(should_continue())

    run_session_loop("test", run_session, lambda: True, stop, poll_interval=0)

    assert seen == [False]


def test_session_restarts_in_next_window_after_returning() -> None:
    """session 正常返回（收盤）後回到待機，下個時段再次啟動新的 session"""
    stop = threading.Event()
    windows = iter([True, False, False, True])  # 啟動 -> 收尾後待機 -> 待機 -> 下個時段
    runs: list[int] = []

    def is_active() -> bool:
        return next(windows, True)

    def run_session(should_continue: ShouldContinue) -> None:
        runs.append(1)
        if len(runs) == 2:
            stop.set()

    run_session_loop("test", run_session, is_active, stop, poll_interval=0)

    assert len(runs) == 2


def test_assumes_active_when_active_check_raises(capsys: pytest.CaptureFixture[str]) -> None:
    stop = threading.Event()
    ran: list[int] = []

    def is_active() -> bool:
        raise ValueError("calendar broken")

    def run_session(should_continue: ShouldContinue) -> None:
        ran.append(1)
        stop.set()

    run_session_loop("test", run_session, is_active, stop, poll_interval=0)

    assert ran == [1]
    assert "保守視為啟用" in capsys.readouterr().out
