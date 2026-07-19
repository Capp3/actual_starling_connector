"""Starling Bank API integration."""

from actual_starling_connector.starling.client import StarlingAPIError, StarlingClient
from actual_starling_connector.starling.models import (
    AccountHolder,
    FeedItem,
    Money,
    StarlingAccount,
)

__all__ = [
    "AccountHolder",
    "FeedItem",
    "Money",
    "StarlingAPIError",
    "StarlingAccount",
    "StarlingClient",
]
