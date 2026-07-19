"""Actual Starling Connector."""

from __future__ import annotations

import argparse

from actual_starling_connector.config import load_settings
from actual_starling_connector.logging import configure_logging, get_logger
from actual_starling_connector.state import open_state_store
from actual_starling_connector.sync import (
    Scheduler,
    SyncWorker,
    default_actual_factory,
    default_starling_factory,
)

__version__ = "0.0.1"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="main",
        description="Starling → Actual sync worker",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single sync cycle and exit (for acceptance / cron)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Load config, configure logging, run scheduler or a single sync cycle."""
    args = _parse_args(argv)
    settings = load_settings()
    configure_logging(settings.log_level)
    log = get_logger("main")
    log.info(
        "startup",
        version=__version__,
        once=args.once,
        sync_channels=[c.holder_type for c in settings.enabled_channels()],
        actual_server_url=str(settings.actual_server_url),
        sync_interval_minutes=settings.sync_interval_minutes,
        log_level=settings.log_level,
        database_path=settings.database_path,
        timezone=settings.timezone,
    )

    store = open_state_store(settings.database_path)
    worker = SyncWorker(
        settings,
        store,
        starling_factory=default_starling_factory(settings),
        actual_factory=default_actual_factory(settings),
    )
    if args.once:
        result = worker.run_once()
        log.info(
            "sync_once_complete",
            fetched=result.fetched,
            imported=result.imported,
            updated=result.updated,
            skipped=result.skipped,
            channels_succeeded=result.channels_succeeded,
            channels_failed=result.channels_failed,
            duration_seconds=result.duration_seconds,
        )
        return

    scheduler = Scheduler(worker, settings.sync_interval_minutes)
    scheduler.run()
