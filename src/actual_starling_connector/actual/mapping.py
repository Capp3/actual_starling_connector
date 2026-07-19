"""Map Starling feed items to Actual import transactions."""

from __future__ import annotations

from decimal import Decimal

from actual_starling_connector.actual.models import ActualTransaction
from actual_starling_connector.starling.models import FeedItem

_CENTS = Decimal(100)


def map_feed_item_to_actual(item: FeedItem) -> ActualTransaction:
    """Convert a Starling feed item into an Actual transaction payload.

    Amounts are major currency units for actualpy (``decimal_to_cents``).
    Starling ``OUT`` becomes negative; ``IN`` becomes positive.
    """
    direction = item.direction.upper()
    signed_minor = item.amount.minor_units
    if direction == "OUT":
        signed_minor = -signed_minor
    elif direction != "IN":
        msg = f"Unsupported Starling direction {item.direction!r}"
        raise ValueError(msg)

    when = item.settlement_time or item.transaction_time
    payee = (item.counter_party_name or "").strip() or "Unknown"
    notes = item.reference.strip() if item.reference else None

    return ActualTransaction(
        date=when.date(),
        amount=Decimal(signed_minor) / _CENTS,
        payee_name=payee,
        imported_id=item.feed_item_uid,
        notes=notes,
        cleared=True,
    )


def map_feed_items_to_actual(items: list[FeedItem]) -> list[ActualTransaction]:
    """Map a list of Starling feed items."""
    return [map_feed_item_to_actual(item) for item in items]
