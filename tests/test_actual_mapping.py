from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from actual_starling_connector.actual.mapping import map_feed_item_to_actual
from actual_starling_connector.starling.models import FeedItem, Money


def _item(**overrides: object) -> FeedItem:
    base = {
        "feedItemUid": "tx-1",
        "categoryUid": "cat-1",
        "amount": {"currency": "GBP", "minorUnits": 1250},
        "sourceAmount": {"currency": "GBP", "minorUnits": 1250},
        "direction": "OUT",
        "transactionTime": "2026-07-01T10:00:00.000Z",
        "updatedAt": "2026-07-01T10:00:01.000Z",
        "settlementTime": "2026-07-01T11:00:00.000Z",
        "status": "SETTLED",
        "counterPartyName": "Coffee Shop",
        "reference": "LATTE",
    }
    base.update(overrides)
    return FeedItem.model_validate(base)


def test_map_outflow_negative_major_units() -> None:
    tx = map_feed_item_to_actual(_item())

    assert tx.imported_id == "tx-1"
    assert tx.amount == Decimal("-12.5")
    assert tx.payee_name == "Coffee Shop"
    assert tx.notes == "LATTE"
    assert tx.cleared is True
    assert tx.date.isoformat() == "2026-07-01"


def test_map_inflow_positive() -> None:
    tx = map_feed_item_to_actual(
        _item(direction="IN", amount={"currency": "GBP", "minorUnits": 5000})
    )

    assert tx.amount == Decimal("50")


def test_map_prefers_settlement_date() -> None:
    tx = map_feed_item_to_actual(
        _item(
            transactionTime="2026-07-01T23:00:00.000Z",
            settlementTime="2026-07-02T01:00:00.000Z",
        )
    )

    assert tx.date.isoformat() == "2026-07-02"


def test_map_falls_back_to_transaction_time() -> None:
    item = _item()
    item = item.model_copy(update={"settlement_time": None})
    tx = map_feed_item_to_actual(item)

    assert tx.date == datetime(2026, 7, 1, 10, 0, tzinfo=UTC).date()


def test_map_unknown_payee_and_empty_reference() -> None:
    tx = map_feed_item_to_actual(_item(counterPartyName="  ", reference=None))

    assert tx.payee_name == "Unknown"
    assert tx.notes is None


def test_map_rejects_unknown_direction() -> None:
    with pytest.raises(ValueError, match="Unsupported Starling direction"):
        map_feed_item_to_actual(_item(direction="SIDEWAYS"))


def test_money_round_trip_alias() -> None:
    money = Money.model_validate({"currency": "GBP", "minorUnits": 1})
    assert money.minor_units == 1
