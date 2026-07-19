from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, text

from actual_starling_connector.state import (
    SyncCheckpoint,
    _coerce_datetime,
    open_state_store,
)


def test_coerce_datetime_branches() -> None:
    assert _coerce_datetime(None) is None
    assert _coerce_datetime(123) is None
    naive = datetime(2026, 1, 2, 3, 4, 5)
    coerced = _coerce_datetime(naive)
    assert coerced == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert _coerce_datetime("2026-07-01T12:00:00Z") == datetime(
        2026, 7, 1, 12, 0, tzinfo=UTC
    )


def test_get_empty_checkpoint(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "sync.db"
    store = open_state_store(db_path)

    checkpoint = store.get("individual")

    assert db_path.is_file()
    assert checkpoint.last_success_at is None
    assert checkpoint.last_transaction_id is None
    assert checkpoint.imported_count == 0
    assert checkpoint.skipped_count == 0


def test_save_and_reload_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "sync.db"
    store = open_state_store(db_path)
    when = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
    original = SyncCheckpoint(
        last_success_at=when,
        last_transaction_id="tx-abc",
        imported_count=3,
        skipped_count=1,
    )

    store.save("joint", original)
    reloaded = open_state_store(db_path).get("joint")

    assert reloaded.last_success_at == when
    assert reloaded.last_transaction_id == "tx-abc"
    assert reloaded.imported_count == 3
    assert reloaded.skipped_count == 1
    assert open_state_store(db_path).get("individual").last_transaction_id is None


def test_keys_are_independent(tmp_path: Path) -> None:
    store = open_state_store(tmp_path / "sync.db")
    store.save(
        "individual",
        SyncCheckpoint(
            last_success_at=datetime(2026, 1, 1, tzinfo=UTC),
            last_transaction_id="tx-ind",
            imported_count=1,
            skipped_count=0,
        ),
    )
    store.save(
        "joint",
        SyncCheckpoint(
            last_success_at=datetime(2026, 2, 2, tzinfo=UTC),
            last_transaction_id="tx-joint",
            imported_count=5,
            skipped_count=2,
        ),
    )

    assert store.get("individual").last_transaction_id == "tx-ind"
    assert store.get("joint").last_transaction_id == "tx-joint"
    assert store.get("joint").imported_count == 5


def test_migrates_legacy_id_row_to_individual(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE sync_checkpoint ("
                "id INTEGER PRIMARY KEY, "
                "last_success_at DATETIME, "
                "last_transaction_id VARCHAR, "
                "imported_count INTEGER NOT NULL, "
                "skipped_count INTEGER NOT NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO sync_checkpoint "
                "(id, last_success_at, last_transaction_id, "
                "imported_count, skipped_count) "
                "VALUES (1, :when, :txid, 4, 1)"
            ),
            {
                # ISO string avoids deprecated sqlite3 datetime adapter (Py3.12+)
                "when": "2026-03-03T00:00:00+00:00",
                "txid": "legacy-tx",
            },
        )
    engine.dispose()

    store = open_state_store(db_path)
    migrated = store.get("individual")

    assert migrated.last_transaction_id == "legacy-tx"
    assert migrated.imported_count == 4
    assert migrated.skipped_count == 1
    assert migrated.last_success_at == datetime(2026, 3, 3, tzinfo=UTC)
    assert store.get("joint").last_transaction_id is None
