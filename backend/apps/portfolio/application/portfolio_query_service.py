from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from apps.portfolio.application.capital_service import CapitalService
from apps.portfolio.domain.entities import AccountCapital, Position
from apps.portfolio.domain.value_objects import Side, direction_sign
from apps.portfolio.infrastructure.price_source import (
    CurrentPriceProvider,
    MarketDataCurrentPriceProvider,
)
from apps.portfolio.infrastructure.repositories import (
    AccountCapitalRepository,
    PositionRepository,
)
from core.services import BaseService


class PortfolioQueryService(BaseService):
    """Read-side aggregation backing the M3 gateways and the read API.

    Implements the approved ADR-028 formulas:

    - ``unrealized_pnl = (current_price - avg_entry_price) x quantity x dir``
    - ``position_exposure = |quantity| x current_price``
    - ``portfolio_exposure = sum(position_exposure)``
    - ``equity = cash + unrealized_pnl_today``

    Current prices come from an injectable :class:`CurrentPriceProvider`
    (production: ``MarketDataService.get_quote``); when a price is unknown the
    position's average entry price is the deterministic fallback (zero
    mark-to-market contribution). See ADR-028 §2.6, §2.7, §11.
    """

    def __init__(
        self,
        position_repo: PositionRepository | None = None,
        capital_repo: AccountCapitalRepository | None = None,
        capital_service: CapitalService | None = None,
        price_source: CurrentPriceProvider | None = None,
    ) -> None:
        super().__init__()
        self._positions = position_repo or PositionRepository()
        self._capitals = capital_repo or AccountCapitalRepository()
        self._capital_service = capital_service or CapitalService(
            capital_repo=self._capitals
        )
        self._prices = price_source or MarketDataCurrentPriceProvider()

    # ------------------------------------------------------------------
    # Aggregations
    # ------------------------------------------------------------------

    def get_current_price(self, symbol: str) -> Decimal | None:
        """Return the latest known price for *symbol*, or ``None``."""
        return self._prices.get_current_price(symbol)

    def get_exposure(self, account_id: uuid.UUID) -> Decimal:
        """Portfolio notional exposure across all open positions (ADR-028 §2.7)."""
        exposure = Decimal(0)
        for position in self._list_open_positions(account_id):
            price = self._prices.get_current_price(position.symbol)
            exposure += abs(position.quantity) * (price or position.avg_entry_price)
        return exposure

    def get_unrealized_pnl(self, account_id: uuid.UUID) -> Decimal:
        """Mark-to-market unrealized P&L across open positions (ADR-028 §2.6)."""
        unrealized = Decimal(0)
        for position in self._list_open_positions(account_id):
            price = self._prices.get_current_price(position.symbol)
            unrealized += (
                ((price or position.avg_entry_price) - position.avg_entry_price)
                * position.quantity
                * direction_sign(position.side)
            )
        return unrealized

    def reconcile_unrealized(self, account_id: uuid.UUID) -> AccountCapital:
        """Persist mark-to-market unrealized P&L and return refreshed capital."""
        unrealized = self.get_unrealized_pnl(account_id)
        state = self._capital_service.reconcile_unrealized(account_id, unrealized)
        return self._to_capital_entity(state)

    def get_daily_loss(self, account_id: uuid.UUID) -> Decimal:
        """Daily loss magnitude for the risk engine (ADR-028 §11).

        Computed as ``min(realized, 0) + min(unrealized, 0)`` from the
        persisted ledger, then normalised to a **non-negative magnitude** so
        it is directly comparable by ``DailyLossLimitCheck``
        (``ctx.daily_loss >= ctx.daily_loss_limit``) exactly like the stub's
        config-driven value.
        """
        state = self._capital_service.get_state(account_id)
        if state is None:
            return Decimal(0)
        loss = min(state.realized_pnl_today, Decimal(0)) + min(
            state.unrealized_pnl_today, Decimal(0)
        )
        return abs(loss)

    def get_account_capital(self, account_id: uuid.UUID) -> AccountCapital | None:
        """Return the account's authoritative capital snapshot, or ``None``."""
        state = self._capital_service.get_state(account_id)
        return self._to_capital_entity(state) if state is not None else None

    def get_available_capital(self, account_id: uuid.UUID) -> Decimal | None:
        state = self._capital_service.get_state(account_id)
        return state.available_capital if state is not None else None

    def get_equity(self, account_id: uuid.UUID) -> Decimal | None:
        state = self._capital_service.get_state(account_id)
        return state.equity if state is not None else None

    def get_open_positions(self, account_id: uuid.UUID) -> list[Position]:
        return self._list_open_positions(account_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _list_open_positions(self, account_id: uuid.UUID) -> list[Position]:
        rows = self._positions.list_open(account_id)
        return [
            Position(
                account_id=row.account_id,
                symbol=row.symbol,
                side=Side(row.side),
                quantity=row.quantity,
                avg_entry_price=row.avg_entry_price,
                opened_at=row.opened_at,
            )
            for row in rows
        ]

    @staticmethod
    def _to_capital_entity(state: Any) -> AccountCapital:
        return AccountCapital(
            account_id=state.account_id,
            cash=state.cash,
            margin_used=state.margin_used,
            equity=state.equity,
            available_capital=state.available_capital,
            realized_pnl_today=state.realized_pnl_today,
            unrealized_pnl_today=state.unrealized_pnl_today,
        )
