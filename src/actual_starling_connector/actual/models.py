"""Models for Actual Budget import payloads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ActualTransaction:
    """Transaction ready for Actual import via actualpy."""

    date: date
    amount: Decimal  # major currency units; outflow negative, inflow positive
    payee_name: str
    imported_id: str
    notes: str | None = None
    cleared: bool = True


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Outcome of an import batch."""

    added: int
    updated: int
    unchanged: int
