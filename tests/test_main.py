from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from actual_starling_connector import main
from actual_starling_connector.config import load_settings
from actual_starling_connector.sync.worker import SyncCycleResult

REQUIRED = {
    "STARLING_INDIVIDUAL_ACCESS_TOKEN": "secret-token",
    "ACTUAL_INDIVIDUAL_ACCOUNT_ID": "account-uuid",
    "ACTUAL_SERVER_URL": "https://actual.example.com",
    "ACTUAL_SYNC_PASSWORD": "secret-password",
    "ACTUAL_BUDGET_SYNC_ID": "budget-sync-id",
}


@pytest.fixture(autouse=True)
def clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [
        *REQUIRED,
        "STARLING_JOINT_ACCESS_TOKEN",
        "ACTUAL_JOINT_ACCOUNT_ID",
        "ACTUAL_DATA_DIR",
        "ACTUAL_ENCRYPTION_PASSWORD",
        "SYNC_INTERVAL_MINUTES",
        "LOG_LEVEL",
        "DATABASE_PATH",
        "TIMEZONE",
        "STARLING_INDIVIDUAL_ACCESS_TOKEN_FILE",
        "ACTUAL_SERVER_URL_FILE",
        "ACTUAL_SYNC_PASSWORD_FILE",
        "ACTUAL_ENCRYPTION_PASSWORD_FILE",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_main_startup_log_omits_secrets_and_runs_scheduler(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: object,
) -> None:
    for key, value in REQUIRED.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "sync.db"))  # type: ignore[operator]

    monkeypatch.setattr(
        "actual_starling_connector.load_settings",
        lambda: load_settings(env_file=None),
    )
    scheduler_run = MagicMock()
    monkeypatch.setattr(
        "actual_starling_connector.Scheduler.run",
        scheduler_run,
    )

    main([])

    scheduler_run.assert_called_once()
    raw = capsys.readouterr().out
    payloads = [json.loads(line) for line in raw.strip().splitlines()]
    startup = next(p for p in payloads if p.get("event") == "startup")
    assert startup["actual_server_url"] == "https://actual.example.com"
    assert startup["sync_channels"] == ["individual"]
    assert startup["once"] is False
    assert "secret-token" not in raw
    assert "secret-password" not in raw
    assert "starling_individual_access_token" not in startup
    assert "actual_sync_password" not in startup


def test_main_once_runs_single_cycle_and_skips_scheduler(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: object,
) -> None:
    for key, value in REQUIRED.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "sync.db"))  # type: ignore[operator]

    monkeypatch.setattr(
        "actual_starling_connector.load_settings",
        lambda: load_settings(env_file=None),
    )
    run_once = MagicMock(
        return_value=SyncCycleResult(
            fetched=1,
            imported=1,
            updated=0,
            skipped=0,
            duration_seconds=0.1,
            last_transaction_id="tx-1",
            channels_succeeded=1,
            channels_failed=0,
        )
    )
    scheduler_run = MagicMock()
    monkeypatch.setattr(
        "actual_starling_connector.SyncWorker.run_once",
        run_once,
    )
    monkeypatch.setattr(
        "actual_starling_connector.Scheduler.run",
        scheduler_run,
    )

    main(["--once"])

    run_once.assert_called_once()
    scheduler_run.assert_not_called()
    raw = capsys.readouterr().out
    payloads = [json.loads(line) for line in raw.strip().splitlines()]
    startup = next(p for p in payloads if p.get("event") == "startup")
    assert startup["once"] is True
    assert any(p.get("event") == "sync_once_complete" for p in payloads)
