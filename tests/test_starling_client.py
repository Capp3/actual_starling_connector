from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from actual_starling_connector.starling import StarlingAPIError, StarlingClient

HOLDER_INDIVIDUAL = {
    "accountHolderUid": "holder-individual",
    "accountHolderType": "INDIVIDUAL",
}

HOLDER_JOINT = {
    "accountHolderUid": "holder-joint",
    "accountHolderType": "JOINT",
}

ACCOUNTS_PAYLOAD = {
    "accounts": [
        {
            "accountUid": "acc-secondary",
            "accountType": "ADDITIONAL",
            "defaultCategory": "cat-secondary",
            "currency": "GBP",
            "name": "Space",
        },
        {
            "accountUid": "acc-primary",
            "accountType": "PRIMARY",
            "defaultCategory": "cat-primary",
            "currency": "GBP",
            "name": "Personal",
        },
    ]
}

FEED_PAYLOAD = {
    "feedItems": [
        {
            "feedItemUid": "tx-settled",
            "categoryUid": "cat-primary",
            "amount": {"currency": "GBP", "minorUnits": 1250},
            "sourceAmount": {"currency": "GBP", "minorUnits": 1250},
            "direction": "OUT",
            "transactionTime": "2026-07-01T10:00:00.000Z",
            "updatedAt": "2026-07-01T10:00:01.000Z",
            "settlementTime": "2026-07-01T10:00:01.000Z",
            "status": "SETTLED",
            "counterPartyName": "Coffee Shop",
            "reference": "LATTE",
        },
        {
            "feedItemUid": "tx-pending",
            "categoryUid": "cat-primary",
            "amount": {"currency": "GBP", "minorUnits": 500},
            "sourceAmount": {"currency": "GBP", "minorUnits": 500},
            "direction": "OUT",
            "transactionTime": "2026-07-02T10:00:00.000Z",
            "updatedAt": "2026-07-02T10:00:01.000Z",
            "status": "PENDING",
            "counterPartyName": "Pending Co",
            "reference": None,
        },
    ]
}


def _client_for(
    handler: Any,
    *,
    account_holder_type: str = "individual",
) -> StarlingClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        transport=transport,
        base_url="https://api.starlingbank.com",
    )
    return StarlingClient(
        "test-token",
        account_holder_type,
        client=http_client,
        max_attempts=3,
        retry_multiplier=0.01,
    )


def _accounts_handler(
    holder_payload: dict[str, str] = HOLDER_INDIVIDUAL,
    accounts_payload: dict[str, Any] = ACCOUNTS_PAYLOAD,
) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/account-holder":
            return httpx.Response(200, json=holder_payload)
        if request.url.path == "/api/v2/accounts":
            return httpx.Response(200, json=accounts_payload)
        return httpx.Response(404, json={"error": "not found"})

    return handler


def test_get_primary_account_prefers_primary() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-token"
        if request.url.path == "/api/v2/account-holder":
            return httpx.Response(200, json=HOLDER_INDIVIDUAL)
        assert request.url.path == "/api/v2/accounts"
        return httpx.Response(200, json=ACCOUNTS_PAYLOAD)

    with _client_for(handler) as client:
        account = client.get_primary_account()

    assert account.account_uid == "acc-primary"
    assert account.default_category_uid == "cat-primary"


def test_get_primary_account_rejects_holder_type_mismatch() -> None:
    with _client_for(
        _accounts_handler(HOLDER_JOINT),
        account_holder_type="individual",
    ) as client:
        with pytest.raises(StarlingAPIError, match="accountHolderType") as exc_info:
            client.get_primary_account()

    assert exc_info.value.status_code == 409


def test_get_primary_account_accepts_joint_when_configured() -> None:
    with _client_for(
        _accounts_handler(HOLDER_JOINT),
        account_holder_type="joint",
    ) as client:
        account = client.get_primary_account()

    assert account.account_uid == "acc-primary"


def test_list_feed_items_settled_only_default() -> None:
    seen_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == (
            "/api/v2/feed/account/acc-primary/category/cat-primary"
        )
        seen_params.update(request.url.params)
        return httpx.Response(200, json=FEED_PAYLOAD)

    with _client_for(handler) as client:
        items = client.list_feed_items(
            "acc-primary",
            "cat-primary",
            datetime(2026, 6, 1, tzinfo=UTC),
        )

    assert seen_params["changesSince"] == "2026-06-01T00:00:00.000Z"
    assert [item.feed_item_uid for item in items] == ["tx-settled"]
    assert items[0].amount.minor_units == 1250
    assert items[0].counter_party_name == "Coffee Shop"


def test_list_feed_items_includes_pending_when_requested() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=FEED_PAYLOAD)

    with _client_for(handler) as client:
        items = client.list_feed_items(
            "acc-primary",
            "cat-primary",
            datetime(2026, 6, 1, tzinfo=UTC),
            settled_only=False,
        )

    assert len(items) == 2


def test_unauthorized_is_not_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"error": "unauthorized"})

    with _client_for(handler) as client:
        with pytest.raises(StarlingAPIError) as exc_info:
            client.get_primary_account()

    assert exc_info.value.status_code == 401
    assert calls["n"] == 1


def test_retries_transient_server_error_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.url.path == "/api/v2/account-holder":
            if calls["n"] < 3:
                return httpx.Response(503, json={"error": "busy"})
            return httpx.Response(200, json=HOLDER_INDIVIDUAL)
        return httpx.Response(200, json=ACCOUNTS_PAYLOAD)

    with _client_for(handler) as client:
        account = client.get_primary_account()

    assert account.account_uid == "acc-primary"
    # 2x 503 + 1x holder 200 + 1x accounts 200
    assert calls["n"] == 4


def test_empty_accounts_raises() -> None:
    with _client_for(_accounts_handler(accounts_payload={"accounts": []})) as client:
        with pytest.raises(StarlingAPIError, match="No Starling accounts"):
            client.get_primary_account()


def test_rejects_empty_access_token() -> None:
    with pytest.raises(ValueError, match="access_token must be non-empty"):
        StarlingClient("", "individual")


def test_rejects_invalid_holder_type() -> None:
    with pytest.raises(ValueError, match="account_holder_type must be one of"):
        StarlingClient("token", "business")


def test_retries_429_using_retry_after_header() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.url.path == "/api/v2/account-holder":
            if calls["n"] == 1:
                return httpx.Response(
                    429,
                    headers={"Retry-After": "0.01"},
                    json={"error": "rate limited"},
                )
            return httpx.Response(200, json=HOLDER_INDIVIDUAL)
        return httpx.Response(200, json=ACCOUNTS_PAYLOAD)

    with _client_for(handler) as client:
        account = client.get_primary_account()

    assert account.account_uid == "acc-primary"
    assert calls["n"] == 3  # 429 + holder 200 + accounts 200


def test_retries_429_with_invalid_retry_after() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.url.path == "/api/v2/account-holder":
            if calls["n"] == 1:
                return httpx.Response(
                    429,
                    headers={"Retry-After": "not-a-number"},
                    json={"error": "rate limited"},
                )
            return httpx.Response(200, json=HOLDER_INDIVIDUAL)
        return httpx.Response(200, json=ACCOUNTS_PAYLOAD)

    with _client_for(handler) as client:
        account = client.get_primary_account()

    assert account.account_uid == "acc-primary"


def test_client_error_4xx_is_not_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(422, json={"error": "unprocessable"})

    with _client_for(handler) as client:
        with pytest.raises(StarlingAPIError) as exc_info:
            client.get_primary_account()

    assert exc_info.value.status_code == 422
    assert calls["n"] == 1


def test_owned_client_closes_on_context_exit() -> None:
    http_client = httpx.Client(
        transport=httpx.MockTransport(_accounts_handler()),
        base_url="https://api.starlingbank.com",
    )
    client = StarlingClient(
        "test-token",
        "individual",
        client=http_client,
        max_attempts=2,
        retry_multiplier=0.01,
    )
    # Force owned-client close path (injected clients normally are not closed)
    client._owns_client = True
    with client:
        account = client.get_primary_account()
    assert account.account_uid == "acc-primary"
    assert http_client.is_closed


def test_retries_transport_error_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.url.path == "/api/v2/account-holder":
            if calls["n"] == 1:
                raise httpx.ConnectError("connection reset")
            return httpx.Response(200, json=HOLDER_INDIVIDUAL)
        return httpx.Response(200, json=ACCOUNTS_PAYLOAD)

    with _client_for(handler) as client:
        account = client.get_primary_account()

    assert account.account_uid == "acc-primary"
    assert calls["n"] == 3
