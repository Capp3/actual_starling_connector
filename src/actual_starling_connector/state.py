"""Durable synchronisation checkpoint store (SQLite via SQLAlchemy)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy import DateTime, Integer, String, create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
)

_LEGACY_HOLDER = "individual"
_SQLITE_ADAPTERS_REGISTERED = False


def _register_sqlite_datetime_adapters() -> None:
    """Use explicit ISO adapters (Python 3.12+ deprecated the defaults)."""
    global _SQLITE_ADAPTERS_REGISTERED
    if _SQLITE_ADAPTERS_REGISTERED:
        return

    def adapt_datetime(value: datetime) -> str:
        aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return aware.astimezone(UTC).isoformat()

    def convert_timestamp(raw: bytes) -> datetime:
        text_value = raw.decode()
        return datetime.fromisoformat(text_value.replace("Z", "+00:00"))

    sqlite3.register_adapter(datetime, adapt_datetime)
    sqlite3.register_converter("timestamp", convert_timestamp)
    sqlite3.register_converter("TIMESTAMP", convert_timestamp)
    _SQLITE_ADAPTERS_REGISTERED = True


def _coerce_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _ensure_utc(value)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        return _ensure_utc(datetime.fromisoformat(normalized))
    return None


@dataclass(frozen=True, slots=True)
class SyncCheckpoint:
    """Minimal persistent sync progress for one Starling holder channel."""

    last_success_at: datetime | None = None
    last_transaction_id: str | None = None
    imported_count: int = 0
    skipped_count: int = 0


class SyncStateStore(Protocol):
    """Storage abstraction for per-holder sync checkpoints."""

    def get(self, holder_type: str) -> SyncCheckpoint:
        """Return checkpoint for ``holder_type``, or empty if none exists."""
        ...

    def save(self, holder_type: str, checkpoint: SyncCheckpoint) -> None:
        """Persist checkpoint for ``holder_type`` (upsert)."""
        ...


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for state tables."""


class SyncCheckpointRow(Base):
    __tablename__ = "sync_checkpoint"

    holder_type: Mapped[str] = mapped_column(String, primary_key=True)
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_transaction_id: Mapped[str | None] = mapped_column(String, nullable=True)
    imported_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _migrate_legacy_checkpoint_table(engine: Engine) -> None:
    """Upgrade pre-M8 ``sync_checkpoint`` (integer ``id`` PK) to keyed schema."""
    insp = inspect(engine)
    if "sync_checkpoint" not in insp.get_table_names():
        return

    columns = {col["name"] for col in insp.get_columns("sync_checkpoint")}
    if "holder_type" in columns:
        return
    if "id" not in columns:
        return

    with engine.begin() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT last_success_at, last_transaction_id, "
                    "imported_count, skipped_count "
                    "FROM sync_checkpoint WHERE id = 1"
                )
            )
            .mappings()
            .first()
        )
        conn.execute(
            text("ALTER TABLE sync_checkpoint RENAME TO sync_checkpoint_legacy")
        )

    Base.metadata.create_all(engine)

    if row is not None:
        with Session(engine) as session:
            session.add(
                SyncCheckpointRow(
                    holder_type=_LEGACY_HOLDER,
                    last_success_at=_coerce_datetime(row["last_success_at"]),
                    last_transaction_id=row["last_transaction_id"],
                    imported_count=int(row["imported_count"] or 0),
                    skipped_count=int(row["skipped_count"] or 0),
                )
            )
            session.commit()

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS sync_checkpoint_legacy"))


class SqliteSyncStateStore:
    """SQLite-backed implementation of ``SyncStateStore``."""

    def __init__(self, database_path: Path | str) -> None:
        path = Path(database_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        _register_sqlite_datetime_adapters()
        self._engine = create_engine(f"sqlite:///{path}", future=True)
        _migrate_legacy_checkpoint_table(self._engine)
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(
            bind=self._engine,
            class_=Session,
            expire_on_commit=False,
        )

    def get(self, holder_type: str) -> SyncCheckpoint:
        with self._session_factory() as session:
            row = session.get(SyncCheckpointRow, holder_type)
            if row is None:
                return SyncCheckpoint()
            return SyncCheckpoint(
                last_success_at=_ensure_utc(row.last_success_at),
                last_transaction_id=row.last_transaction_id,
                imported_count=row.imported_count,
                skipped_count=row.skipped_count,
            )

    def save(self, holder_type: str, checkpoint: SyncCheckpoint) -> None:
        with self._session_factory() as session:
            row = session.get(SyncCheckpointRow, holder_type)
            if row is None:
                row = SyncCheckpointRow(holder_type=holder_type)
                session.add(row)
            row.last_success_at = _ensure_utc(checkpoint.last_success_at)
            row.last_transaction_id = checkpoint.last_transaction_id
            row.imported_count = checkpoint.imported_count
            row.skipped_count = checkpoint.skipped_count
            session.commit()


def open_state_store(database_path: Path | str) -> SyncStateStore:
    """Open (and initialise) a SQLite sync state store at ``database_path``."""
    return SqliteSyncStateStore(database_path)
