"""Shared test builders (importable from test modules)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from actual_starling_connector.config import Settings
from actual_starling_connector.starling.models import FeedItem


def make_settings(**overrides: Any) -> Settings:
    """Build Settings with individual-channel defaults (no ``.env`` file)."""
    base: dict[str, Any] = {
        "starling_individual_access_token": "token-ind",
        "actual_individual_account_id": "acct-ind",
        "actual_server_url": "https://actual.example.com",
        "actual_sync_password": "password",
        "actual_budget_sync_id": "budget-id",
        "_env_file": None,
    }
    base.update(overrides)
    return Settings(**base)


def make_feed_item(uid: str, when: datetime) -> FeedItem:
    """Minimal settled OUT feed item for worker/mapping tests."""
    stamp = when.isoformat().replace("+00:00", "Z")
    return FeedItem.model_validate(
        {
            "feedItemUid": uid,
            "categoryUid": "cat-1",
            "amount": {"currency": "GBP", "minorUnits": 100},
            "sourceAmount": {"currency": "GBP", "minorUnits": 100},
            "direction": "OUT",
            "transactionTime": stamp,
            "updatedAt": stamp,
            "settlementTime": stamp,
            "status": "SETTLED",
            "counterPartyName": "Shop",
            "reference": None,
        }
    )
