"""Interval scheduler with graceful shutdown and overlap skipping."""

from __future__ import annotations

import signal
import threading
from collections.abc import Callable
from types import FrameType
from typing import Any, Protocol

from actual_starling_connector.logging import get_logger


class _RunnableWorker(Protocol):
    def run_once(self) -> object: ...


class Scheduler:
    """Run sync cycles on an interval until SIGINT/SIGTERM (or ``stop()``)."""

    def __init__(
        self,
        worker: _RunnableWorker,
        interval_minutes: int,
        *,
        stop_event: threading.Event | None = None,
        install_signals: bool = True,
        thread_factory: Callable[..., threading.Thread] | None = None,
    ) -> None:
        if interval_minutes < 1:
            msg = "interval_minutes must be >= 1"
            raise ValueError(msg)
        self._worker = worker
        self._interval_seconds = interval_minutes * 60
        self._stop = stop_event or threading.Event()
        self._install_signals = install_signals
        self._thread_factory = thread_factory or threading.Thread
        self._cycle_thread: threading.Thread | None = None
        self._log = get_logger("scheduler")
        self._previous_handlers: dict[int, Any] = {}

    def stop(self) -> None:
        """Request a graceful stop (same as SIGINT/SIGTERM)."""
        self._stop.set()

    def run(self) -> None:
        """Run cycles until stopped. First cycle starts immediately."""
        self._install_signal_handlers()
        self._log.info(
            "scheduler_start",
            interval_minutes=self._interval_seconds // 60,
        )
        try:
            while not self._stop.is_set():
                self._tick()
                self._stop.wait(timeout=self._interval_seconds)
            self._join_cycle()
        finally:
            self._restore_signal_handlers()
            self._log.info("scheduler_stop")

    def _tick(self) -> None:
        if self._cycle_thread is not None and self._cycle_thread.is_alive():
            self._log.warning("sync_cycle_skipped_overlap")
            return
        thread = self._thread_factory(
            target=self._run_cycle,
            name="sync-cycle",
            daemon=True,
        )
        self._cycle_thread = thread
        thread.start()

    def _run_cycle(self) -> None:
        try:
            self._worker.run_once()
        except Exception:
            self._log.exception("sync_cycle_error_continuing")

    def _join_cycle(self) -> None:
        if self._cycle_thread is not None and self._cycle_thread.is_alive():
            self._log.info("scheduler_waiting_for_in_flight_cycle")
            self._cycle_thread.join()

    def _handle_signal(self, signum: int, _frame: FrameType | None) -> None:
        self._log.info("scheduler_signal_received", signal=signum)
        self.stop()

    def _install_signal_handlers(self) -> None:
        if not self._install_signals:
            return
        for sig in (signal.SIGINT, signal.SIGTERM):
            self._previous_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, self._handle_signal)

    def _restore_signal_handlers(self) -> None:
        for sig, handler in self._previous_handlers.items():
            signal.signal(sig, handler)
        self._previous_handlers.clear()
