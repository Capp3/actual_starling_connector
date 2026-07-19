from __future__ import annotations

import threading
import time

import pytest

from actual_starling_connector.logging import configure_logging
from actual_starling_connector.sync.scheduler import Scheduler


@pytest.fixture(autouse=True)
def _configure_logging() -> None:
    configure_logging("INFO")


class FakeWorker:
    def __init__(self, *, block: threading.Event | None = None) -> None:
        self.calls = 0
        self.started = threading.Event()
        self.block = block
        self.errors_before_success = 0
        self.lock = threading.Lock()

    def run_once(self) -> str:
        with self.lock:
            self.calls += 1
            call_no = self.calls
        self.started.set()
        if self.errors_before_success > 0 and call_no <= self.errors_before_success:
            raise RuntimeError(f"boom-{call_no}")
        if self.block is not None:
            self.block.wait(timeout=5)
        return "ok"


def _run_scheduler(scheduler: Scheduler) -> threading.Thread:
    thread = threading.Thread(target=scheduler.run, name="scheduler-test", daemon=True)
    thread.start()
    return thread


def test_runs_first_cycle_immediately() -> None:
    worker = FakeWorker()
    stop = threading.Event()
    scheduler = Scheduler(
        worker,
        interval_minutes=60,
        stop_event=stop,
        install_signals=False,
    )
    thread = _run_scheduler(scheduler)

    assert worker.started.wait(timeout=2)
    stop.set()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert worker.calls >= 1


def test_stop_interrupts_sleep() -> None:
    worker = FakeWorker()
    stop = threading.Event()
    scheduler = Scheduler(
        worker,
        interval_minutes=60,
        stop_event=stop,
        install_signals=False,
    )
    started = time.monotonic()
    thread = _run_scheduler(scheduler)
    assert worker.started.wait(timeout=2)
    stop.set()
    thread.join(timeout=2)
    elapsed = time.monotonic() - started
    assert not thread.is_alive()
    assert elapsed < 5


def test_skips_overlap_when_cycle_still_running() -> None:
    release = threading.Event()
    worker = FakeWorker(block=release)
    stop = threading.Event()
    # Tiny interval via subclassing wait by using 1 minute but forcing tick:
    # Drive ticks manually through a custom scheduler loop helper.
    scheduler = Scheduler(
        worker,
        interval_minutes=1,
        stop_event=stop,
        install_signals=False,
    )

    scheduler._tick()
    assert worker.started.wait(timeout=2)
    scheduler._tick()  # should skip while first cycle blocked
    release.set()
    scheduler._join_cycle()
    assert worker.calls == 1


def test_cycle_error_does_not_stop_scheduler() -> None:
    worker = FakeWorker()
    worker.errors_before_success = 1
    stop = threading.Event()
    scheduler = Scheduler(
        worker,
        interval_minutes=60,
        stop_event=stop,
        install_signals=False,
    )
    thread = _run_scheduler(scheduler)
    assert worker.started.wait(timeout=2)
    # Allow first failing cycle thread to finish, then force another tick.
    time.sleep(0.05)
    worker.started.clear()
    scheduler._tick()
    assert worker.started.wait(timeout=2)
    stop.set()
    thread.join(timeout=2)
    assert worker.calls >= 2


def test_interval_minutes_must_be_at_least_one() -> None:
    with pytest.raises(ValueError, match="interval_minutes must be >= 1"):
        Scheduler(FakeWorker(), interval_minutes=0, install_signals=False)


def test_stop_sets_event() -> None:
    stop = threading.Event()
    scheduler = Scheduler(
        FakeWorker(),
        interval_minutes=60,
        stop_event=stop,
        install_signals=False,
    )
    assert not stop.is_set()
    scheduler.stop()
    assert stop.is_set()


def test_handle_signal_requests_stop() -> None:
    stop = threading.Event()
    scheduler = Scheduler(
        FakeWorker(),
        interval_minutes=60,
        stop_event=stop,
        install_signals=False,
    )
    scheduler._handle_signal(15, None)
    assert stop.is_set()
