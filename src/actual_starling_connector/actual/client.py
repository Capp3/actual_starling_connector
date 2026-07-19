"""Actual Budget client wrapper around actualpy."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Self

from actual import Actual
from actual.queries import get_account, get_accounts, reconcile_transaction
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from actual_starling_connector.actual.models import ActualTransaction, ImportResult

ActualFactory = Callable[..., Any]


class ActualClientError(Exception):
    """Raised when Actual import or session setup fails."""


class ActualClient:
    """Download a budget and import transactions via actualpy."""

    def __init__(
        self,
        server_url: str,
        password: str,
        budget_sync_id: str,
        *,
        data_dir: str | Path = "data/actual",
        encryption_password: str | None = None,
        extra_headers: dict[str, str] | None = None,
        actual_factory: ActualFactory | None = None,
        max_attempts: int = 3,
        retry_multiplier: float = 0.5,
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._password = password
        self._budget_sync_id = budget_sync_id
        self._data_dir = Path(data_dir)
        self._encryption_password = encryption_password
        self._extra_headers = dict(extra_headers) if extra_headers else None
        self._actual_factory = actual_factory or Actual
        self._max_attempts = max_attempts
        self._retry_multiplier = retry_multiplier
        self._actual: Any | None = None

    def __enter__(self) -> Self:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._actual = self._actual_factory(
                base_url=self._server_url,
                password=self._password,
                file=self._budget_sync_id,
                encryption_password=self._encryption_password,
                data_dir=str(self._data_dir),
                extra_headers=self._extra_headers,
            )
            self._actual.__enter__()
        except Exception as exc:
            msg = f"Failed to open Actual session: {exc}"
            raise ActualClientError(msg) from exc
        self._download_budget()
        return self

    def __exit__(self, *args: object) -> None:
        if self._actual is not None:
            self._actual.__exit__(*args)
            self._actual = None

    def import_transactions(
        self,
        account_id: str,
        transactions: list[ActualTransaction],
    ) -> ImportResult:
        """Reconcile transactions into the given Actual account and commit."""
        if self._actual is None:
            msg = "ActualClient must be used as a context manager"
            raise ActualClientError(msg)

        session = self._actual.session
        account = get_account(session, account_id)
        if account is None:
            available = [
                f"{a.name!r} ({a.id})" for a in get_accounts(session, closed=False)
            ]
            listed = ", ".join(available) if available else "(none)"
            msg = (
                f"Actual account not found: {account_id!r}. "
                f"Set ACTUAL_ACCOUNT_ID to an account id or name. Available: {listed}"
            )
            raise ActualClientError(msg)

        already_matched: list[Any] = []
        for tx in transactions:
            row = reconcile_transaction(
                session,
                tx.date,
                account,
                tx.payee_name,
                tx.notes,
                None,
                tx.amount,
                imported_id=tx.imported_id,
                cleared=tx.cleared,
                already_matched=already_matched,
            )
            already_matched.append(row)

        added, updated, unchanged = _count_session_results(session, already_matched)
        self._commit()
        return ImportResult(added=added, updated=updated, unchanged=unchanged)

    def _download_budget(self) -> None:
        assert self._actual is not None
        try:
            self._retrying(self._actual.download_budget)
        except Exception as exc:
            msg = f"Failed to download Actual budget: {exc}"
            raise ActualClientError(msg) from exc

    def _commit(self) -> None:
        assert self._actual is not None
        try:
            self._retrying(self._actual.commit)
        except Exception as exc:
            msg = f"Failed to commit Actual changes: {exc}"
            raise ActualClientError(msg) from exc

    def _retrying(self, func: Callable[[], Any]) -> Any:
        @retry(
            retry=retry_if_exception_type(Exception),
            wait=wait_exponential(
                multiplier=self._retry_multiplier,
                min=self._retry_multiplier,
                max=8,
            ),
            stop=stop_after_attempt(self._max_attempts),
            reraise=True,
        )
        def _do() -> Any:
            return func()

        return _do()


def _count_session_results(session: Any, rows: list[Any]) -> tuple[int, int, int]:
    # SQLAlchemy ORM instances are typically unhashable; compare by identity.
    new_ids = {id(obj) for obj in getattr(session, "new", ())}
    dirty_ids = {id(obj) for obj in getattr(session, "dirty", ())}
    added = updated = unchanged = 0
    for row in rows:
        row_id = id(row)
        if row_id in new_ids:
            added += 1
        elif row_id in dirty_ids:
            updated += 1
        else:
            unchanged += 1
    return added, updated, unchanged
