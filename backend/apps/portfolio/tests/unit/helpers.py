from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from apps.eventbus.domain.events import DomainEvent


@dataclass
class FakePriceSource:
    """Deterministic current-price map for mark-to-market math."""

    prices: dict[str, Decimal] = field(default_factory=dict)

    def get_current_price(self, symbol: str) -> Decimal | None:
        return self.prices.get(symbol)


def make_account_capital(
    *,
    account_id: uuid.UUID,
    cash: str = "1000000",
    margin_used: str = "0",
    realized_pnl_today: str = "0",
    unrealized_pnl_today: str = "0",
) -> dict[str, Any]:
    """Build the raw field dict the domain entity serializes from."""
    return {
        "account_id": account_id,
        "cash": Decimal(cash),
        "margin_used": Decimal(margin_used),
        "realized_pnl_today": Decimal(realized_pnl_today),
        "unrealized_pnl_today": Decimal(unrealized_pnl_today),
    }


def make_fill_payload(
    *,
    symbol: str = "RELIANCE",
    side: str = "LONG",
    quantity: str = "100",
    price: str = "100.00",
) -> dict[str, Any]:
    """Build the payload for a manual/paper fill recording call."""
    return {
        "account_id": str(uuid.uuid4()),
        "symbol": symbol,
        "side": side,
        "quantity": Decimal(quantity),
        "price": Decimal(price),
    }


def published_events_of_type(
    events: list[DomainEvent], event_type: str
) -> list[DomainEvent]:
    return [e for e in events if e.event_type == event_type]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
