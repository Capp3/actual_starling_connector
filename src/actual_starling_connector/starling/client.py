"""Starling Bank Customer API client."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Self

import httpx
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from actual_starling_connector.starling.models import (
    AccountHolder,
    AccountsResponse,
    FeedItem,
    FeedItemsResponse,
    StarlingAccount,
)

DEFAULT_BASE_URL = "https://api.starlingbank.com"
_SETTLED_STATUS = "SETTLED"
_NON_RETRYABLE_STATUS = frozenset({401, 403, 404})

# Config value -> Starling accountHolderType
_HOLDER_TYPE_TO_API = {
    "individual": "INDIVIDUAL",
    "joint": "JOINT",
}


class StarlingAPIError(Exception):
    """Raised when the Starling API returns an error response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TimeoutException | httpx.TransportError):
        return True
    if isinstance(exc, StarlingAPIError):
        if exc.status_code is None:
            return False
        if exc.status_code in _NON_RETRYABLE_STATUS:
            return False
        return exc.status_code == 429 or exc.status_code >= 500
    return False


def _format_changes_since(value: datetime) -> str:
    utc = (
        value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    )
    millis = utc.microsecond // 1000
    return f"{utc.strftime('%Y-%m-%dT%H:%M:%S')}.{millis:03d}Z"


def _parse_retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


class StarlingClient:
    """Minimal Starling client for account discovery and incremental feed fetch."""

    def __init__(
        self,
        access_token: str,
        account_holder_type: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.Client | None = None,
        max_attempts: int = 5,
        retry_multiplier: float = 0.5,
    ) -> None:
        if not access_token:
            msg = "access_token must be non-empty"
            raise ValueError(msg)
        normalized = account_holder_type.strip().lower()
        if normalized not in _HOLDER_TYPE_TO_API:
            allowed = ", ".join(sorted(_HOLDER_TYPE_TO_API))
            msg = (
                f"account_holder_type must be one of: {allowed}; "
                f"got {account_holder_type!r}"
            )
            raise ValueError(msg)
        self._account_holder_type = normalized
        self._expected_api_holder_type = _HOLDER_TYPE_TO_API[normalized]
        self._max_attempts = max_attempts
        self._retry_multiplier = retry_multiplier
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=30.0,
        )
        if client is not None and "Authorization" not in client.headers:
            self._client.headers["Authorization"] = f"Bearer {access_token}"

    def _wait_strategy(self, retry_state: RetryCallState) -> float:
        exc = (
            retry_state.outcome.exception() if retry_state.outcome is not None else None
        )
        if isinstance(exc, StarlingAPIError) and exc.retry_after is not None:
            return float(exc.retry_after)
        wait = wait_exponential(
            multiplier=self._retry_multiplier,
            min=self._retry_multiplier,
            max=8,
        )
        return float(wait(retry_state))

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def get_account_holder(self) -> AccountHolder:
        """Return the account holder bound to this access token."""
        payload = self._request_json("GET", "/api/v2/account-holder")
        return AccountHolder.model_validate(payload)

    def get_primary_account(self) -> StarlingAccount:
        """Validate holder type, then return the primary (or first) account."""
        holder = self.get_account_holder()
        actual_type = holder.account_holder_type.upper()
        if actual_type != self._expected_api_holder_type:
            msg = (
                f"Starling token accountHolderType is {actual_type!r}, "
                f"but channel holder_type={self._account_holder_type!r} "
                f"expects {self._expected_api_holder_type!r}. "
                "Use a personal access token for that holder type "
                "(individual and joint are separate tokens)."
            )
            raise StarlingAPIError(msg, status_code=409)

        payload = self._request_json("GET", "/api/v2/accounts")
        accounts = AccountsResponse.model_validate(payload).accounts
        if not accounts:
            msg = "No Starling accounts returned"
            raise StarlingAPIError(msg, status_code=404)

        for account in accounts:
            if (account.account_type or "").upper() == "PRIMARY":
                return account
        return accounts[0]

    def list_feed_items(
        self,
        account_uid: str,
        category_uid: str,
        changes_since: datetime,
        *,
        settled_only: bool = True,
    ) -> list[FeedItem]:
        """Fetch feed items changed since ``changes_since``."""
        params = {"changesSince": _format_changes_since(changes_since)}
        path = f"/api/v2/feed/account/{account_uid}/category/{category_uid}"
        payload = self._request_json("GET", path, params=params)
        items = FeedItemsResponse.model_validate(payload).feed_items
        if settled_only:
            return [item for item in items if item.status.upper() == _SETTLED_STATUS]
        return items

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> Any:
        @retry(
            retry=retry_if_exception(_is_retryable),
            wait=self._wait_strategy,
            stop=stop_after_attempt(self._max_attempts),
            reraise=True,
        )
        def _do_request() -> Any:
            try:
                response = self._client.request(method, path, params=params)
            except httpx.TimeoutException:
                raise
            except httpx.TransportError:
                raise

            if response.status_code in _NON_RETRYABLE_STATUS:
                raise StarlingAPIError(
                    f"Starling API {response.status_code} for {method} {path}",
                    status_code=response.status_code,
                )

            if response.status_code == 429 or response.status_code >= 500:
                raise StarlingAPIError(
                    f"Starling API {response.status_code} for {method} {path}",
                    status_code=response.status_code,
                    retry_after=_parse_retry_after(response),
                )

            if response.status_code >= 400:
                raise StarlingAPIError(
                    f"Starling API {response.status_code} for {method} {path}",
                    status_code=response.status_code,
                )

            return response.json()

        return _do_request()
