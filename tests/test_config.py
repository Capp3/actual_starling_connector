from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from actual_starling_connector.config import apply_file_secrets, load_settings

SHARED = {
    "ACTUAL_SERVER_URL": "https://actual.example.com",
    "ACTUAL_SYNC_PASSWORD": "sync-password",
    "ACTUAL_BUDGET_SYNC_ID": "budget-sync-id",
}

INDIVIDUAL = {
    "STARLING_INDIVIDUAL_ACCESS_TOKEN": "individual-token",
    "ACTUAL_INDIVIDUAL_ACCOUNT_ID": "actual-individual",
}

JOINT = {
    "STARLING_JOINT_ACCESS_TOKEN": "joint-token",
    "ACTUAL_JOINT_ACCOUNT_ID": "actual-joint",
}


@pytest.fixture(autouse=True)
def clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    keys = [
        *SHARED,
        *INDIVIDUAL,
        *JOINT,
        "ACTUAL_DATA_DIR",
        "ACTUAL_ENCRYPTION_PASSWORD",
        "ACTUAL_CF_ACCESS_CLIENT_ID",
        "ACTUAL_CF_ACCESS_CLIENT_SECRET",
        "SYNC_INTERVAL_MINUTES",
        "LOG_LEVEL",
        "DATABASE_PATH",
        "TIMEZONE",
        "STARLING_INDIVIDUAL_ACCESS_TOKEN_FILE",
        "STARLING_JOINT_ACCESS_TOKEN_FILE",
        "ACTUAL_SERVER_URL_FILE",
        "ACTUAL_SYNC_PASSWORD_FILE",
        "ACTUAL_ENCRYPTION_PASSWORD_FILE",
        "ACTUAL_CF_ACCESS_CLIENT_ID_FILE",
        "ACTUAL_CF_ACCESS_CLIENT_SECRET_FILE",
        # legacy ignored keys
        "STARLING_ACCESS_TOKEN",
        "STARLING_ACCOUNT_HOLDER_TYPE",
        "ACTUAL_ACCOUNT_ID",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def test_load_settings_both_channels(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {**SHARED, **INDIVIDUAL, **JOINT}.items():
        monkeypatch.setenv(key, value)

    settings = load_settings(env_file=None)
    channels = settings.enabled_channels()

    assert [c.holder_type for c in channels] == ["individual", "joint"]
    assert channels[0].access_token == "individual-token"
    assert channels[0].actual_account_id == "actual-individual"
    assert channels[1].access_token == "joint-token"
    assert channels[1].actual_account_id == "actual-joint"


def test_individual_only(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {**SHARED, **INDIVIDUAL}.items():
        monkeypatch.setenv(key, value)

    settings = load_settings(env_file=None)

    assert [c.holder_type for c in settings.enabled_channels()] == ["individual"]


def test_joint_only(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {**SHARED, **JOINT}.items():
        monkeypatch.setenv(key, value)

    settings = load_settings(env_file=None)

    assert [c.holder_type for c in settings.enabled_channels()] == ["joint"]


def test_no_channels_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in SHARED.items():
        monkeypatch.setenv(key, value)

    with pytest.raises(ValidationError, match="at least one sync channel"):
        load_settings(env_file=None)


def test_individual_xor_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in SHARED.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("STARLING_INDIVIDUAL_ACCESS_TOKEN", "token-only")

    with pytest.raises(ValidationError, match="Individual channel requires both"):
        load_settings(env_file=None)


def test_joint_xor_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in SHARED.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("STARLING_JOINT_ACCESS_TOKEN", "joint-token-only")

    with pytest.raises(ValidationError, match="Joint channel requires both"):
        load_settings(env_file=None)


def test_file_secrets_load(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    token_path = tmp_path / "starling_token"
    url_path = tmp_path / "actual_url"
    password_path = tmp_path / "actual_password"
    token_path.write_text("file-token\n", encoding="utf-8")
    url_path.write_text("https://from-file.example.com\n", encoding="utf-8")
    password_path.write_text("file-password\n", encoding="utf-8")

    monkeypatch.setenv("STARLING_INDIVIDUAL_ACCESS_TOKEN_FILE", str(token_path))
    monkeypatch.setenv("ACTUAL_INDIVIDUAL_ACCOUNT_ID", "actual-individual")
    monkeypatch.setenv("ACTUAL_SERVER_URL_FILE", str(url_path))
    monkeypatch.setenv("ACTUAL_SYNC_PASSWORD_FILE", str(password_path))
    monkeypatch.setenv("ACTUAL_BUDGET_SYNC_ID", "budget-sync-id")

    settings = load_settings(env_file=None)

    assert settings.starling_individual_access_token == "file-token"
    assert settings.actual_server_url == "https://from-file.example.com"
    assert settings.actual_sync_password == "file-password"


def test_file_secret_prefers_file_over_direct(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    token_path = tmp_path / "starling_token"
    token_path.write_text("from-file", encoding="utf-8")

    monkeypatch.setenv("STARLING_INDIVIDUAL_ACCESS_TOKEN", "from-env")
    monkeypatch.setenv("STARLING_INDIVIDUAL_ACCESS_TOKEN_FILE", str(token_path))
    monkeypatch.setenv("ACTUAL_INDIVIDUAL_ACCOUNT_ID", "actual-individual")
    for key, value in SHARED.items():
        monkeypatch.setenv(key, value)

    apply_file_secrets()
    settings = load_settings(env_file=None)

    assert settings.starling_individual_access_token == "from-file"


def test_invalid_log_level_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {**SHARED, **INDIVIDUAL}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("LOG_LEVEL", "VERBOSE")

    with pytest.raises(ValidationError):
        load_settings(env_file=None)


def test_legacy_env_keys_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {**SHARED, **INDIVIDUAL}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("STARLING_ACCESS_TOKEN", "legacy")
    monkeypatch.setenv("STARLING_ACCOUNT_HOLDER_TYPE", "business")
    monkeypatch.setenv("ACTUAL_ACCOUNT_ID", "legacy-acct")

    settings = load_settings(env_file=None)

    assert len(settings.enabled_channels()) == 1
