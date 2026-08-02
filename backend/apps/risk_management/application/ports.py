from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol


class CapitalGateway(Protocol):
    """Port for account capital/equity state.

    M3 has no real capital producer yet (apps.accounts.Account carries no
    balance field). Until a portfolio milestone lands, the production wiring
    uses :class:`StubPortfolioStateGateway` with config-driven values,
    clearly logged as non-production.
    """

    def get_available_capital(self) -> Decimal | None:
        """Return available trading capital, or ``None`` when unknown."""

    def get_max_position_size(self) -> int:
        """Return the configured absolute cap on any single position size."""


class PortfolioStateGateway(Protocol):
    """Port for portfolio-level exposure and daily P&L state.

    Same non-production caveat as :class:`CapitalGateway`: the stub returns
    zero exposure / zero daily loss until a real portfolio app exists.
    """

    implementation_name: str
    """Stable name of the producing gateway (e.g. ``"stub"``). Persisted on
    every RiskDecision so downstream consumers can prove which source backed
    the evaluation — the M3 guardrail against the stub backing a real order."""

    def get_current_exposure(self) -> Decimal:
        """Return the current portfolio exposure (notional)."""

    def get_daily_loss(self) -> Decimal:
        """Return the realized (+ unrealized, when available) daily loss."""

    def get_instrument_max_qty(self, symbol: str) -> int | None:
        """Return an instrument-level quantity cap, or ``None`` for none."""

    def get_tradable_symbols(self) -> frozenset[str]:
        """Return the set of symbols currently tradable."""


class MarketStatusGateway(Protocol):
    """Port for market-hours / freshness determination."""

    def is_market_open(self, reference_dt: datetime) -> bool:
        """Return whether the NSE market is open at ``reference_dt``."""

    def is_fresh(self, occurred_at: datetime, reference_dt: datetime) -> bool:
        """Return whether the firing's data is fresh relative to now."""
