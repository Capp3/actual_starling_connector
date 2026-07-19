from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Self
from unittest.mock import MagicMock, patch

import pytest

from actual_starling_connector.actual.models import ActualTransaction, ImportResult
from actual_starling_connector.config import SyncChannel
from actual_starling_connector.logging import configure_logging
from actual_starling_connector.starling.models import FeedItem, StarlingAccount
from actual_starling_connector.state import SyncCheckpoint, open_state_store
from actual_starling_connector.sync import FIRST_SYNC_LOOKBACK_DAYS, SyncWorker
from actual_starling_connector.sync.worker import (
    default_actual_factory,
    default_starling_factory,
)
from helpers import make_feed_item, make_settings

FIXED_NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _configure_logging() -> None:
    configure_logging("INFO")


_settings = make_settings
_feed_item = make_feed_item


class FakeStarling:
    def __init__(self, items: list[FeedItem], *, fail: bool = False) -> None:
        self.items = items
        self.fail = fail
        self.changes_since: datetime | None = None
        self.channel: SyncChannel | None = None

    def __enter__(self) -> Self:
        if self.fail:
            msg = "starling down"
            raise RuntimeError(msg)
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def get_primary_account(self) -> StarlingAccount:
        return StarlingAccount.model_validate(
            {
                "accountUid": "starling-acc",
                "defaultCategory": "cat-1",
                "currency": "GBP",
                "accountType": "PRIMARY",
                "name": "Personal",
            }
        )

    def list_feed_items(
        self,
        account_uid: str,
        category_uid: str,
        changes_since: datetime,
        *,
        settled_only: bool = True,
    ) -> list[FeedItem]:
        self.changes_since = changes_since
        return list(self.items)


class FakeActual:
    def __init__(
        self,
        results: dict[str, ImportResult | Exception] | ImportResult | Exception,
    ) -> None:
        self.results = results
        self.imported_by_account: dict[str, list[ActualTransaction]] = {}

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def import_transactions(
        self, account_id: str, transactions: list[ActualTransaction]
    ) -> ImportResult:
        self.imported_by_account[account_id] = list(transactions)
        result = (
            self.results
            if not isinstance(self.results, dict)
            else self.results[account_id]
        )
        if isinstance(result, Exception):
            raise result
        return result


def test_empty_feed_advances_checkpoint_with_lookback(tmp_path: Any) -> None:
    store = open_state_store(tmp_path / "sync.db")
    starling = FakeStarling([])
    actual = FakeActual(ImportResult(added=0, updated=0, unchanged=0))

    worker = SyncWorker(
        _settings(),
        store,
        starling_factory=lambda channel: starling,
        actual_factory=lambda: actual,
        clock=lambda: FIXED_NOW,
    )
    result = worker.run_once()

    assert result.fetched == 0
    assert result.imported == 0
    assert result.channels_succeeded == 1
    assert starling.changes_since == FIXED_NOW - timedelta(
        days=FIRST_SYNC_LOOKBACK_DAYS
    )
    saved = store.get("individual")
    assert saved.last_success_at == FIXED_NOW
    assert saved.last_transaction_id is None


def test_success_imports_and_saves_latest_txn_id(tmp_path: Any) -> None:
    store = open_state_store(tmp_path / "sync.db")
    store.save(
        "individual",
        SyncCheckpoint(
            last_success_at=FIXED_NOW - timedelta(days=1),
            last_transaction_id="old",
            imported_count=0,
            skipped_count=0,
        ),
    )
    older = _feed_item("tx-old", FIXED_NOW - timedelta(hours=2))
    newer = _feed_item("tx-new", FIXED_NOW - timedelta(hours=1))
    starling = FakeStarling([older, newer])
    actual = FakeActual(ImportResult(added=2, updated=0, unchanged=0))

    worker = SyncWorker(
        _settings(),
        store,
        starling_factory=lambda channel: starling,
        actual_factory=lambda: actual,
        clock=lambda: FIXED_NOW,
    )
    result = worker.run_once()

    assert result.fetched == 2
    assert result.imported == 2
    assert result.last_transaction_id == "tx-new"
    assert starling.changes_since == FIXED_NOW - timedelta(days=1)
    assert len(actual.imported_by_account["acct-ind"]) == 2
    saved = store.get("individual")
    assert saved.last_success_at == FIXED_NOW
    assert saved.last_transaction_id == "tx-new"
    assert saved.imported_count == 2


def test_import_failure_is_fail_closed(tmp_path: Any) -> None:
    store = open_state_store(tmp_path / "sync.db")
    prior = SyncCheckpoint(
        last_success_at=FIXED_NOW - timedelta(days=3),
        last_transaction_id="prior-tx",
        imported_count=1,
        skipped_count=0,
    )
    store.save("individual", prior)
    starling = FakeStarling([_feed_item("tx-1", FIXED_NOW - timedelta(hours=1))])
    actual = FakeActual(RuntimeError("actual down"))

    worker = SyncWorker(
        _settings(),
        store,
        starling_factory=lambda channel: starling,
        actual_factory=lambda: actual,
        clock=lambda: FIXED_NOW,
    )

    with pytest.raises(RuntimeError, match="actual down"):
        worker.run_once()

    saved = store.get("individual")
    assert saved.last_success_at == prior.last_success_at
    assert saved.last_transaction_id == "prior-tx"
    assert saved.imported_count == 1


def test_two_channels_both_succeed(tmp_path: Any) -> None:
    store = open_state_store(tmp_path / "sync.db")
    clients = {
        "individual": FakeStarling(
            [_feed_item("tx-i", FIXED_NOW - timedelta(hours=1))]
        ),
        "joint": FakeStarling([_feed_item("tx-j", FIXED_NOW - timedelta(hours=1))]),
    }
    actual = FakeActual(
        {
            "acct-ind": ImportResult(added=1, updated=0, unchanged=0),
            "acct-joint": ImportResult(added=1, updated=0, unchanged=0),
        }
    )

    worker = SyncWorker(
        _settings(
            starling_joint_access_token="token-joint",
            actual_joint_account_id="acct-joint",
        ),
        store,
        starling_factory=lambda channel: clients[channel.holder_type],
        actual_factory=lambda: actual,
        clock=lambda: FIXED_NOW,
    )
    result = worker.run_once()

    assert result.channels_succeeded == 2
    assert result.channels_failed == 0
    assert result.fetched == 2
    assert result.imported == 2
    assert store.get("individual").last_transaction_id == "tx-i"
    assert store.get("joint").last_transaction_id == "tx-j"


def test_one_channel_failure_does_not_block_other(tmp_path: Any) -> None:
    store = open_state_store(tmp_path / "sync.db")
    clients = {
        "individual": FakeStarling([], fail=True),
        "joint": FakeStarling([_feed_item("tx-j", FIXED_NOW - timedelta(hours=1))]),
    }
    actual = FakeActual(
        {
            "acct-ind": ImportResult(added=0, updated=0, unchanged=0),
            "acct-joint": ImportResult(added=1, updated=0, unchanged=0),
        }
    )

    worker = SyncWorker(
        _settings(
            starling_joint_access_token="token-joint",
            actual_joint_account_id="acct-joint",
        ),
        store,
        starling_factory=lambda channel: clients[channel.holder_type],
        actual_factory=lambda: actual,
        clock=lambda: FIXED_NOW,
    )
    result = worker.run_once()

    assert result.channels_succeeded == 1
    assert result.channels_failed == 1
    assert result.imported == 1
    assert store.get("individual").last_success_at is None
    assert store.get("joint").last_transaction_id == "tx-j"


def test_second_run_with_unchanged_imports(tmp_path: Any) -> None:
    store = open_state_store(tmp_path / "sync.db")
    item = _feed_item("tx-1", FIXED_NOW - timedelta(hours=1))
    starling = FakeStarling([item])
    actual = FakeActual(ImportResult(added=0, updated=0, unchanged=1))

    worker = SyncWorker(
        _settings(),
        store,
        starling_factory=lambda channel: starling,
        actual_factory=lambda: actual,
        clock=lambda: FIXED_NOW,
    )
    result = worker.run_once()

    assert result.imported == 0
    assert result.skipped == 1
    assert store.get("individual").skipped_count == 1


def test_all_channels_fail_raises(tmp_path: Any) -> None:
    store = open_state_store(tmp_path / "sync.db")
    clients = {
        "individual": FakeStarling([], fail=True),
        "joint": FakeStarling([], fail=True),
    }
    actual = FakeActual(ImportResult(added=0, updated=0, unchanged=0))

    worker = SyncWorker(
        _settings(
            starling_joint_access_token="token-joint",
            actual_joint_account_id="acct-joint",
        ),
        store,
        starling_factory=lambda channel: clients[channel.holder_type],
        actual_factory=lambda: actual,
        clock=lambda: FIXED_NOW,
    )

    with pytest.raises(RuntimeError, match="starling down"):
        worker.run_once()


def test_default_starling_factory_uses_channel_token() -> None:
    settings = _settings()
    channel = SyncChannel(
        holder_type="individual",
        access_token="channel-token",
        actual_account_id="acct-ind",
    )
    with patch("actual_starling_connector.sync.worker.StarlingClient") as mock_client:
        factory = default_starling_factory(settings)
        factory(channel)
        mock_client.assert_called_once_with("channel-token", "individual")


def test_default_actual_factory_passes_cf_and_encryption() -> None:
    settings = _settings(
        actual_cf_access_client_id="cf-id",
        actual_cf_access_client_secret="cf-secret",
        actual_encryption_password="enc-pass",
        actual_data_dir="/data/actual",
    )
    with patch("actual_starling_connector.sync.worker.ActualClient") as mock_client:
        mock_client.return_value = MagicMock()
        factory = default_actual_factory(settings)
        factory()
        mock_client.assert_called_once_with(
            settings.actual_server_url,
            settings.actual_sync_password,
            settings.actual_budget_sync_id,
            data_dir="/data/actual",
            encryption_password="enc-pass",
            extra_headers={
                "CF-Access-Client-Id": "cf-id",
                "CF-Access-Client-Secret": "cf-secret",
            },
        )


def test_default_actual_factory_omits_cf_when_incomplete() -> None:
    settings = _settings(actual_cf_access_client_id="cf-id-only")
    with patch("actual_starling_connector.sync.worker.ActualClient") as mock_client:
        mock_client.return_value = MagicMock()
        factory = default_actual_factory(settings)
        factory()
        kwargs = mock_client.call_args.kwargs
        assert kwargs["extra_headers"] is None
        assert kwargs["encryption_password"] is None
