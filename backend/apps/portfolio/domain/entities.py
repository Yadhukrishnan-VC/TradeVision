from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from apps.portfolio.domain.value_objects import Side


@dataclass(frozen=True)
class Position:
    """Immutable snapshot of an open position (Portfolio's write model).

    One instance per open ``(account_id, symbol)``. This is deliberately
    distinct from dashboard's read-model ``PositionSnapshot`` and from the AI
    context ``core.events.PositionSnapshot`` — see ADR-028 §2.1.

    Attributes:
        account_id:       Owning account UUID.
        symbol:           Instrument symbol (e.g. ``"RELIANCE"``).
        side:             ``LONG`` or ``SHORT``.
        quantity:         Open quantity (always > 0).
        avg_entry_price:  Weighted-average entry price (Decimal).
        opened_at:        UTC datetime the position was opened.
    """

    account_id: UUID
    symbol: str
    side: Side
    quantity: Decimal
    avg_entry_price: Decimal
    opened_at: datetime

    @property
    def notional(self) -> Decimal:
        """Position notional = |quantity| x avg_entry_price (ADR-028 §2.7)."""
        return abs(self.quantity) * self.avg_entry_price


@dataclass(frozen=True)
class AccountCapital:
    """Immutable snapshot of an account's authoritative capital state.

    Mirrors the ``AccountCapitalState`` persistence row. ``equity`` and
    ``available_capital`` are always consistent with the ledger fields:
    ``equity = cash + unrealized_pnl_today`` and
    ``available_capital = cash - margin_used`` (ADR-028 §2.3).
    """

    account_id: UUID
    cash: Decimal
    margin_used: Decimal
    equity: Decimal
    available_capital: Decimal
    realized_pnl_today: Decimal
    unrealized_pnl_today: Decimal
