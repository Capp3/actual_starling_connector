"""Environment-driven application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SECRET_ENV_NAMES = (
    "STARLING_INDIVIDUAL_ACCESS_TOKEN",
    "STARLING_JOINT_ACCESS_TOKEN",
    "ACTUAL_SERVER_URL",
    "ACTUAL_SYNC_PASSWORD",
    "ACTUAL_ENCRYPTION_PASSWORD",
    "ACTUAL_CF_ACCESS_CLIENT_ID",
    "ACTUAL_CF_ACCESS_CLIENT_SECRET",
)

_VALID_LOG_LEVELS = frozenset(
    {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
)

HolderType = Literal["individual", "joint"]


@dataclass(frozen=True, slots=True)
class SyncChannel:
    """One Starling holder → one Actual account mapping."""

    holder_type: HolderType
    access_token: str
    actual_account_id: str


def apply_file_secrets() -> None:
    """Load Docker-style ``*_FILE`` secrets into the matching env vars.

    If ``NAME_FILE`` is set, its file contents replace ``NAME`` (stripped).
    """
    for name in _SECRET_ENV_NAMES:
        file_path = os.environ.get(f"{name}_FILE")
        if not file_path:
            continue
        os.environ[name] = Path(file_path).read_text(encoding="utf-8").strip()


def _nonempty(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class Settings(BaseSettings):
    """Runtime configuration from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    starling_individual_access_token: str | None = None
    starling_joint_access_token: str | None = None
    actual_individual_account_id: str | None = None
    actual_joint_account_id: str | None = None
    actual_server_url: str
    actual_sync_password: str
    actual_budget_sync_id: str
    actual_data_dir: str = "data/actual"
    actual_encryption_password: str | None = None
    actual_cf_access_client_id: str | None = None
    actual_cf_access_client_secret: str | None = None
    sync_interval_minutes: int = Field(default=60, ge=1)
    log_level: str = "INFO"
    database_path: str = "data/sync.db"
    timezone: str = "UTC"

    @field_validator(
        "starling_individual_access_token",
        "starling_joint_access_token",
        "actual_individual_account_id",
        "actual_joint_account_id",
        mode="before",
    )
    @classmethod
    def blank_to_none(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            return _nonempty(value)
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in _VALID_LOG_LEVELS:
            allowed = ", ".join(sorted(_VALID_LOG_LEVELS))
            msg = f"Invalid LOG_LEVEL {value!r}; expected one of: {allowed}"
            raise ValueError(msg)
        return level

    @model_validator(mode="after")
    def validate_sync_channels(self) -> Settings:
        individual_token = self.starling_individual_access_token
        individual_account = self.actual_individual_account_id
        joint_token = self.starling_joint_access_token
        joint_account = self.actual_joint_account_id

        if bool(individual_token) ^ bool(individual_account):
            msg = (
                "Individual channel requires both "
                "STARLING_INDIVIDUAL_ACCESS_TOKEN and ACTUAL_INDIVIDUAL_ACCOUNT_ID"
            )
            raise ValueError(msg)
        if bool(joint_token) ^ bool(joint_account):
            msg = (
                "Joint channel requires both "
                "STARLING_JOINT_ACCESS_TOKEN and ACTUAL_JOINT_ACCOUNT_ID"
            )
            raise ValueError(msg)
        if not individual_token and not joint_token:
            msg = (
                "Configure at least one sync channel: individual "
                "(STARLING_INDIVIDUAL_ACCESS_TOKEN + ACTUAL_INDIVIDUAL_ACCOUNT_ID) "
                "and/or joint "
                "(STARLING_JOINT_ACCESS_TOKEN + ACTUAL_JOINT_ACCOUNT_ID)"
            )
            raise ValueError(msg)
        return self

    def enabled_channels(self) -> list[SyncChannel]:
        """Return fully configured sync channels in stable order."""
        channels: list[SyncChannel] = []
        if self.starling_individual_access_token and self.actual_individual_account_id:
            channels.append(
                SyncChannel(
                    holder_type="individual",
                    access_token=self.starling_individual_access_token,
                    actual_account_id=self.actual_individual_account_id,
                )
            )
        if self.starling_joint_access_token and self.actual_joint_account_id:
            channels.append(
                SyncChannel(
                    holder_type="joint",
                    access_token=self.starling_joint_access_token,
                    actual_account_id=self.actual_joint_account_id,
                )
            )
        return channels


def load_settings(*, env_file: str | Path | None = ".env") -> Settings:
    """Apply ``*_FILE`` secrets, then validate settings.

    Pass ``env_file=None`` to ignore a local ``.env`` file (useful in tests).
    """
    apply_file_secrets()
    return Settings(_env_file=env_file)
