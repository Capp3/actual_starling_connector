"""Structured JSON logging setup."""

from __future__ import annotations

import importlib
import sys
from typing import Any

import structlog

_stdlib_logging = importlib.import_module("logging")


def configure_logging(level: str) -> None:
    """Configure structlog + stdlib logging for JSON logs on stdout."""
    log_level = getattr(_stdlib_logging, level.upper())

    _stdlib_logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.format_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        # Bind stdout at emit time (avoids closed pytest capture streams).
        logger_factory=lambda *args: structlog.PrintLogger(sys.stdout),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str | None = None) -> Any:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)
