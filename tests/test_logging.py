from __future__ import annotations

import json

from actual_starling_connector.logging import configure_logging, get_logger


def test_configure_logging_emits_json(capsys: object) -> None:
    configure_logging("INFO")
    log = get_logger("test")
    log.info("hello", answer=42)

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    payload = json.loads(captured.out.strip().splitlines()[-1])
    assert payload["event"] == "hello"
    assert payload["answer"] == 42
    assert payload["level"] == "info"
    assert "timestamp" in payload


def test_get_logger_after_configure() -> None:
    configure_logging("DEBUG")
    log = get_logger("test")
    assert hasattr(log, "info")
