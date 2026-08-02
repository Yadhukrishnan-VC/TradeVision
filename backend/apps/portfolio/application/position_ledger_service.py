from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from django.db import transaction

from apps.portfolio.application.capital_service import CapitalService
from apps.portfolio.application.portfolio_query_service import PortfolioQueryService
from apps.portfolio.domain.exceptions import InvalidFillError
from apps.portfolio.domain.value_objects import (
    Side,
    direction_sign,
    opposite_side,
)
from apps.portfolio.infrastructure.event_publishers import PortfolioEventPublisher
from apps.portfolio.infrastructure.models import Position
from apps.portfolio.infrastructure.repositories import (
    PositionFillExecutionRepository,
    PositionRepository,
)
from core.services import BaseService


class PositionLedgerService(BaseService):
    """Ledger-style position lifecycle (ADR-028 §2.5, §2.6, §18).

    Position changes are driven exclusively through ``record_fill`` /
    ``close_position`` / ``adjust_quantity`` — there is no broker import and
    no parallel execution path (ADR-028 §2.13). Every call is idempotent on
    ``source_fill_id`` and applies the position change, the capital effect
    (margin + realized P&L) and the approved event publishes in one DB
    transaction (ADR-028 §8).

    Lifecycle (ADR-028 §18)::
        none -> PositionOpened -> PositionQuantityChanged* -> PositionClosed
    Opposite-side fills that over-offset close the position and reopen on the
    other side (explicit edge case, not a silent assumption).
    """

    def __init__(
        self,
        position_repo: PositionRepository | None = None,
        fill_repo: PositionFillExecutionRepository | None = None,
        capital_service: CapitalService | None = None,
        event_publisher: PortfolioEventPublisher | None = None,
        query_service: PortfolioQueryService | None = None,
    ) -> None:
        super().__init__()
        self._positions = position_repo or PositionRepository()
        self._fills = fill_repo or PositionFillExecutionRepository()
        self._capital = capital_service or CapitalService()
        self._events = event_publisher or PortfolioEventPublisher()
        self._queries = query_service or PortfolioQueryService()

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def record_fill(
        self,
        account_id: uuid.UUID,
        symbol: str,
        side: Side,
        quantity: Decimal,
        price: Decimal,
        occurred_at: datetime | None = None,
        *,
        source_fill_id: uuid.UUID | None = None,
        correlation_id: uuid.UUID | None = None,
        causation_id: uuid.UUID | None = None,
    ) -> Position | None:
        """Apply a fill to the ledger (idempotent on ``source_fill_id``).

        Returns the resulting open position; ``None`` when the fill fully
        closed the position or was a duplicate delivery.

        ``source_fill_id`` is the idempotency key (supplied by a future broker
        adapter or generated here for manual reconciliation). ``correlation_id``
        defaults to the fill id; pass a ``RiskApproved.correlation_id`` when
        the fill responds to an approved risk decision.
        """
        self._validate_fill(symbol, side, quantity, price)
        occurred_at = occurred_at or datetime.now(timezone.utc)
        source_fill_id = source_fill_id or uuid.uuid4()
        correlation_id = correlation_id or source_fill_id

        with transaction.atomic():
            execution = self._fills.create_from_fill(
                source_fill_id=source_fill_id,
                account_id=account_id,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                applied_at=occurred_at,
            )
            if execution is None:
                self._logger.warning(
                    "duplicate_fill_skipped",
                    extra={
                        "source_fill_id": str(source_fill_id),
                        "account_id": str(account_id),
                        "symbol": symbol,
                    },
                )
                return None

            position = self._apply_fill(
                account_id, symbol, side, quantity, price, occurred_at,
                correlation_id=correlation_id, causation_id=causation_id,
            )

        self._publish_exposure_changed(account_id, correlation_id)
        return position

    def close_position(
        self,
        account_id: uuid.UUID,
        symbol: str,
        exit_price: Decimal,
        occurred_at: datetime | None = None,
        *,
        source_fill_id: uuid.UUID | None = None,
        correlation_id: uuid.UUID | None = None,
        causation_id: uuid.UUID | None = None,
    ) -> Position | None:
        """Close the open position for (account_id, symbol) at *exit_price*.

        Reuses ``record_fill`` (idempotent, margin release + realized P&L +
        ``PositionClosed``) so closing can never fork the position logic.
        Returns ``None`` when no position is open.
        """
        existing = self._positions.get_open(account_id, symbol)
        if existing is None:
            return None
        return self.record_fill(
            account_id,
            symbol,
            opposite_side(Side(existing.side)),
            existing.quantity,
            exit_price,
            occurred_at=occurred_at,
            source_fill_id=source_fill_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

    def adjust_quantity(
        self,
        account_id: uuid.UUID,
        symbol: str,
        side: Side,
        new_quantity: Decimal,
        price: Decimal,
        occurred_at: datetime | None = None,
        *,
        source_fill_id: uuid.UUID | None = None,
        correlation_id: uuid.UUID | None = None,
        causation_id: uuid.UUID | None = None,
    ) -> Position | None:
        """Scale a position to *new_quantity* (scale-in / scale-out).

        Expresses the adjustment as a fill of the delta in the correct
        direction so every path (increase, partial decrease, full close,
        over-offset flip) flows through the single ``record_fill`` logic.
        """
        if new_quantity < 0:
            raise InvalidFillError(
                f"Quantity cannot be negative: {new_quantity}",
                code="INVALID_QUANTITY",
            )
        existing = self._positions.get_open(account_id, symbol)
        if existing is None:
            if new_quantity == 0:
                return None
            return self.record_fill(
                account_id, symbol, side, new_quantity, price,
                occurred_at=occurred_at, source_fill_id=source_fill_id,
                correlation_id=correlation_id, causation_id=causation_id,
            )

        current = existing.quantity
        if new_quantity == current:
            return existing
        delta = new_quantity - current
        if delta > 0:
            return self.record_fill(
                account_id, symbol, Side(existing.side), delta, price,
                occurred_at=occurred_at, source_fill_id=source_fill_id,
                correlation_id=correlation_id, causation_id=causation_id,
            )
        return self.record_fill(
            account_id, symbol, opposite_side(Side(existing.side)), abs(delta), price,
            occurred_at=occurred_at, source_fill_id=source_fill_id,
            correlation_id=correlation_id, causation_id=causation_id,
        )

    # ------------------------------------------------------------------
    # Fill application (ADR-028 §18)
    # ------------------------------------------------------------------

    def _apply_fill(
        self,
        account_id: uuid.UUID,
        symbol: str,
        side: Side,
        quantity: Decimal,
        price: Decimal,
        occurred_at: datetime,
        *,
        correlation_id: uuid.UUID,
        causation_id: uuid.UUID | None,
    ) -> Position | None:
        existing = self._positions.get_open(account_id, symbol)

        if existing is None:
            position = self._positions.create_open(
                account_id, symbol, side, quantity, price, occurred_at
            )
            self._capital.reserve_margin(
                account_id, quantity * price,
                correlation_id=correlation_id, causation_id=causation_id,
            )
            self._events.publish_position_opened(
                position_id=position.id,
                account_id=account_id,
                symbol=symbol,
                side=side.value,
                quantity=quantity,
                entry_price=price,
                correlation_id=correlation_id,
                causation_id=causation_id,
            )
            return position

        if existing.side == side.value:
            return self._apply_add(
                account_id, existing, side, quantity, price,
                correlation_id=correlation_id, causation_id=causation_id,
            )
        return self._apply_opposite(
            account_id, existing, side, quantity, price,
            correlation_id=correlation_id, causation_id=causation_id,
        )

    def _apply_add(
        self,
        account_id: uuid.UUID,
        existing: Position,
        side: Side,
        quantity: Decimal,
        price: Decimal,
        *,
        correlation_id: uuid.UUID,
        causation_id: uuid.UUID | None,
    ) -> Position:
        """Same-direction fill: increase quantity, reweight average entry."""
        old_qty = existing.quantity
        new_qty = old_qty + quantity
        new_avg = (
            (existing.avg_entry_price * old_qty) + (price * quantity)
        ) / new_qty
        position = self._positions.update_open(
            account_id, existing.symbol,
            quantity=new_qty, avg_entry_price=new_avg,
        )
        self._capital.reserve_margin(
            account_id, quantity * price,
            correlation_id=correlation_id, causation_id=causation_id,
        )
        self._events.publish_position_quantity_changed(
            position_id=position.id,
            account_id=account_id,
            quantity=new_qty,
            entry_price=new_avg,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
        return position

    def _apply_opposite(
        self,
        account_id: uuid.UUID,
        existing: Position,
        side: Side,
        quantity: Decimal,
        price: Decimal,
        *,
        correlation_id: uuid.UUID,
        causation_id: uuid.UUID | None,
    ) -> Position | None:
        """Opposite-direction fill: partial close, full close, or flip."""
        sign = direction_sign(Side(existing.side))
        if quantity == existing.quantity:
            return self._apply_full_close(
                account_id, existing, price, correlation_id=correlation_id,
                causation_id=causation_id,
            )

        if quantity < existing.quantity:
            new_qty = existing.quantity - quantity
            realized = (price - existing.avg_entry_price) * quantity * sign
            position = self._positions.update_open(
                account_id, existing.symbol,
                quantity=new_qty, avg_entry_price=existing.avg_entry_price,
            )
            self._capital.release_margin(
                account_id, quantity * existing.avg_entry_price,
                correlation_id=correlation_id, causation_id=causation_id,
            )
            self._capital.record_realized_pnl(
                account_id, realized,
                correlation_id=correlation_id, causation_id=causation_id,
            )
            self._events.publish_position_quantity_changed(
                position_id=position.id,
                account_id=account_id,
                quantity=new_qty,
                entry_price=position.avg_entry_price,
                correlation_id=correlation_id,
                causation_id=causation_id,
            )
            return position

        # Over-offset: close fully, realize on the old quantity, reopen opposite.
        realized = (price - existing.avg_entry_price) * existing.quantity * sign
        self._positions.close(account_id, existing.symbol)
        self._capital.release_margin(
            account_id, existing.quantity * existing.avg_entry_price,
            correlation_id=correlation_id, causation_id=causation_id,
        )
        self._capital.record_realized_pnl(
            account_id, realized,
            correlation_id=correlation_id, causation_id=causation_id,
        )
        self._events.publish_position_closed(
            position_id=existing.id,
            account_id=account_id,
            symbol=existing.symbol,
            side=existing.side,
            entry_price=existing.avg_entry_price,
            exit_price=price,
            quantity=existing.quantity,
            realized_pnl=realized,
            realized_pnl_pct=self._realized_pnl_pct(realized, existing),
            holding_period_seconds=self._holding_period_seconds(existing.opened_at),
            opened_at=existing.opened_at,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
        return self._apply_fill(
            account_id,
            existing.symbol,
            side,
            quantity - existing.quantity,
            price,
            datetime.now(timezone.utc),
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

    def _apply_full_close(
        self,
        account_id: uuid.UUID,
        existing: Position,
        price: Decimal,
        *,
        correlation_id: uuid.UUID,
        causation_id: uuid.UUID | None,
    ) -> Position:
        """Quantity matches exactly: close the position and realize P&L."""
        sign = direction_sign(Side(existing.side))
        realized = (price - existing.avg_entry_price) * existing.quantity * sign
        self._positions.close(account_id, existing.symbol)
        self._capital.release_margin(
            account_id, existing.quantity * existing.avg_entry_price,
            correlation_id=correlation_id, causation_id=causation_id,
        )
        self._capital.record_realized_pnl(
            account_id, realized,
            correlation_id=correlation_id, causation_id=causation_id,
        )
        self._events.publish_position_closed(
            position_id=existing.id,
            account_id=account_id,
            symbol=existing.symbol,
            side=existing.side,
            entry_price=existing.avg_entry_price,
            exit_price=price,
            quantity=existing.quantity,
            realized_pnl=realized,
            realized_pnl_pct=self._realized_pnl_pct(realized, existing),
            holding_period_seconds=self._holding_period_seconds(existing.opened_at),
            opened_at=existing.opened_at,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
        return None

    def _publish_exposure_changed(self, account_id: uuid.UUID, correlation_id: uuid.UUID) -> None:
        exposure = self._queries.get_exposure(account_id)
        self._events.publish_exposure_changed(
            account_id=account_id,
            exposure=exposure,
            correlation_id=correlation_id,
        )

    @staticmethod
    def _realized_pnl_pct(realized: Decimal, position: Position) -> Decimal:
        """Realized P&L as a percentage of the position's opening notional."""
        notional = position.avg_entry_price * position.quantity
        if notional == 0:
            return Decimal(0)
        return (realized / notional) * Decimal(100)

    @staticmethod
    def _holding_period_seconds(opened_at: datetime) -> int:
        return max(
            0,
            int((datetime.now(timezone.utc) - opened_at).total_seconds()),
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_fill(
        symbol: str, side: Side, quantity: Decimal, price: Decimal
    ) -> None:
        if not symbol:
            raise InvalidFillError("Symbol is required", code="INVALID_SYMBOL")
        if not isinstance(side, Side):
            raise InvalidFillError(f"Invalid side: {side!r}", code="INVALID_SIDE")
        if quantity is None or quantity <= 0:
            raise InvalidFillError(
                f"Quantity must be positive, got {quantity!r}",
                code="INVALID_QUANTITY",
            )
        if price is None or price <= 0:
            raise InvalidFillError(
                f"Price must be positive, got {price!r}",
                code="INVALID_PRICE",
            )
