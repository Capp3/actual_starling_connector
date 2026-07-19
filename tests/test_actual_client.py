from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest

from actual_starling_connector.actual.client import (
    ActualClient,
    ActualClientError,
    _count_session_results,
)
from actual_starling_connector.actual.models import ActualTransaction


class _UnhashableRow:
    """Mimics SQLAlchemy ORM instances that cannot be put in a set."""

    __hash__ = None  # type: ignore[assignment]

    def __init__(self, name: str) -> None:
        self.name = name


class _FakeSession:
    def __init__(self) -> None:
        self.new: list[Any] = []
        self.dirty: list[Any] = []


class _FakeActual:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self.session = _FakeSession()
        self.downloaded = False
        self.committed = False
        self.kwargs = kwargs

    def __enter__(self) -> _FakeActual:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def download_budget(self) -> None:
        self.downloaded = True

    def commit(self) -> None:
        self.committed = True


def test_import_transactions_reconciles_and_commits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    fake = _FakeActual()
    account = object()
    created_rows: list[Any] = []

    def fake_get_account(session: Any, account_id: str) -> object:
        assert account_id == "acct-1"
        assert session is fake.session
        return account

    def fake_reconcile(
        session: Any,
        tx_date: date,
        acct: object,
        payee: str,
        notes: str | None,
        category: object,
        amount: Decimal,
        imported_id: str | None = None,
        cleared: bool | None = None,
        already_matched: list[Any] | None = None,
        **kwargs: object,
    ) -> object:
        row = MagicMock(name=imported_id)
        session.new.append(row)
        created_rows.append(
            {
                "date": tx_date,
                "payee": payee,
                "notes": notes,
                "amount": amount,
                "imported_id": imported_id,
                "cleared": cleared,
                "account": acct,
            }
        )
        return row

    monkeypatch.setattr(
        "actual_starling_connector.actual.client.get_account", fake_get_account
    )
    monkeypatch.setattr(
        "actual_starling_connector.actual.client.reconcile_transaction",
        fake_reconcile,
    )

    txs = [
        ActualTransaction(
            date=date(2026, 7, 1),
            amount=Decimal("-12.50"),
            payee_name="Coffee",
            imported_id="tx-1",
            notes="LATTE",
        )
    ]

    with ActualClient(
        "https://actual.example.com",
        "password",
        "budget-sync-id",
        data_dir=tmp_path,  # type: ignore[arg-type]
        actual_factory=lambda **kwargs: fake,
        retry_multiplier=0.01,
    ) as client:
        result = client.import_transactions("acct-1", txs)

    assert fake.downloaded is True
    assert fake.committed is True
    assert result.added == 1
    assert result.updated == 0
    assert result.unchanged == 0
    assert created_rows[0]["imported_id"] == "tx-1"
    assert created_rows[0]["amount"] == Decimal("-12.5")


def test_missing_account_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    fake = _FakeActual()
    monkeypatch.setattr(
        "actual_starling_connector.actual.client.get_account",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "actual_starling_connector.actual.client.get_accounts",
        lambda *_args, **_kwargs: [],
    )

    with ActualClient(
        "https://actual.example.com",
        "password",
        "budget-sync-id",
        data_dir=tmp_path,  # type: ignore[arg-type]
        actual_factory=lambda **kwargs: fake,
        retry_multiplier=0.01,
    ) as client:
        with pytest.raises(ActualClientError, match="account not found"):
            client.import_transactions("missing", [])


def test_import_without_context_manager_fails() -> None:
    client = ActualClient("https://actual.example.com", "password", "budget-id")
    with pytest.raises(ActualClientError, match="context manager"):
        client.import_transactions("acct", [])


def test_count_session_results_with_unhashable_rows() -> None:
    session = _FakeSession()
    added_row = _UnhashableRow("new")
    dirty_row = _UnhashableRow("dirty")
    unchanged_row = _UnhashableRow("same")
    session.new.append(added_row)
    session.dirty.append(dirty_row)

    added, updated, unchanged = _count_session_results(
        session, [added_row, dirty_row, unchanged_row]
    )

    assert (added, updated, unchanged) == (1, 1, 1)


def test_enter_session_open_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    class _BoomActual:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> _BoomActual:
            msg = "auth failed"
            raise RuntimeError(msg)

        def __exit__(self, *args: object) -> None:
            return None

    with (
        pytest.raises(ActualClientError, match="Failed to open Actual session"),
        ActualClient(
            "https://actual.example.com",
            "password",
            "budget-sync-id",
            data_dir=tmp_path,  # type: ignore[arg-type]
            actual_factory=lambda **kwargs: _BoomActual(),
            retry_multiplier=0.01,
        ),
    ):
        pass


def test_download_budget_failure_wrapped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    class _FailDownload(_FakeActual):
        def download_budget(self) -> None:
            msg = "network down"
            raise RuntimeError(msg)

    with pytest.raises(ActualClientError, match="Failed to download Actual budget"):
        with ActualClient(
            "https://actual.example.com",
            "password",
            "budget-sync-id",
            data_dir=tmp_path,  # type: ignore[arg-type]
            actual_factory=lambda **kwargs: _FailDownload(),
            retry_multiplier=0.01,
            max_attempts=1,
        ):
            pass


def test_commit_failure_wrapped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    fake = _FakeActual()

    def boom_commit() -> None:
        msg = "commit failed"
        raise RuntimeError(msg)

    fake.commit = boom_commit  # type: ignore[method-assign]
    monkeypatch.setattr(
        "actual_starling_connector.actual.client.get_account",
        lambda *_a, **_k: object(),
    )
    monkeypatch.setattr(
        "actual_starling_connector.actual.client.reconcile_transaction",
        lambda *_a, **_k: MagicMock(),
    )

    with ActualClient(
        "https://actual.example.com",
        "password",
        "budget-sync-id",
        data_dir=tmp_path,  # type: ignore[arg-type]
        actual_factory=lambda **kwargs: fake,
        retry_multiplier=0.01,
        max_attempts=1,
    ) as client:
        with pytest.raises(ActualClientError, match="Failed to commit Actual changes"):
            client.import_transactions(
                "acct-1",
                [
                    ActualTransaction(
                        date=date(2026, 7, 1),
                        amount=Decimal("-1.00"),
                        payee_name="X",
                        imported_id="tx-1",
                    )
                ],
            )
