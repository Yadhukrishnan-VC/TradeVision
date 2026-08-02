from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from apps.eventbus.application.ports import EventBus
from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.portfolio.domain.value_objects import CapitalAdjustmentReason


class PortfolioEventPublisher:
    """Publish the five events approved by ADR-028 §2.10.

    Namespaces and payload shapes match the *existing, unmodified* dashboard
    consumers exactly (``positions.*`` for the dormant
    ``position_projection_service`` contract; ``portfolio.*`` for the new
    capital/exposure territory). Every event carries ``account_id`` because
    ``BaseProjectionService._get_account_id`` reads
    ``event.payload["account_id"]`` unconditionally.

    Decimal payload values are rendered through :meth:`_fmt`, which strips the
    trailing-zero padding Django's ``DecimalField`` (``decimal_places=8``)
    adds on read-back, so consumers receive the natural numeric form
    (``"200"`` not ``"200.00000000"``).

    ``correlation_id`` is the triggering fill/adjustment id (or the
    originating ``RiskApproved.correlation_id``); ``causation_id`` is the
    immediate cause event id.
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._bus = event_bus or get_event_bus()

    @staticmethod
    def _fmt(value: Decimal) -> str:
        """Render a Decimal in its natural numeric form (no trailing zeros)."""
        return format(value.normalize(), "f")

    # ------------------------------------------------------------------
    # positions.* — dashboard already subscribes (unmodified)
    # ------------------------------------------------------------------

    def publish_position_opened(
        self,
        *,
        position_id: UUID,
        account_id: UUID,
        symbol: str,
        side: str,
        quantity: Decimal,
        entry_price: Decimal,
        correlation_id: UUID,
        causation_id: UUID | None = None,
    ) -> DomainEvent:
        return self._publish(
            "positions.PositionOpened",
            payload={
                "account_id": str(account_id),
                "position_id": str(position_id),
                "symbol": symbol,
                "side": side,
                "quantity": self._fmt(quantity),
                "entry_price": self._fmt(entry_price),
            },
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

    def publish_position_quantity_changed(
        self,
        *,
        position_id: UUID,
        account_id: UUID,
        quantity: Decimal,
        entry_price: Decimal,
        correlation_id: UUID,
        causation_id: UUID | None = None,
    ) -> DomainEvent:
        return self._publish(
            "positions.PositionQuantityChanged",
            payload={
                "account_id": str(account_id),
                "position_id": str(position_id),
                "quantity": self._fmt(quantity),
                "entry_price": self._fmt(entry_price),
            },
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

    def publish_position_closed(
        self,
        *,
        position_id: UUID,
        account_id: UUID,
        symbol: str,
        side: str,
        entry_price: Decimal,
        exit_price: Decimal,
        quantity: Decimal,
        realized_pnl: Decimal,
        realized_pnl_pct: Decimal,
        holding_period_seconds: int,
        opened_at: datetime,
        correlation_id: UUID,
        causation_id: UUID | None = None,
    ) -> DomainEvent:
        return self._publish(
            "positions.PositionClosed",
            payload={
                "account_id": str(account_id),
                "position_id": str(position_id),
                "symbol": symbol,
                "side": side,
                "entry_price": self._fmt(entry_price),
                "exit_price": self._fmt(exit_price),
                "quantity": self._fmt(quantity),
                "realized_pnl": self._fmt(realized_pnl),
                "realized_pnl_pct": self._fmt(realized_pnl_pct),
                "holding_period_seconds": str(holding_period_seconds),
                "opened_at": opened_at.isoformat(),
            },
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

    # ------------------------------------------------------------------
    # portfolio.* — new territory, no existing consumer to collide with
    # ------------------------------------------------------------------

    def publish_account_capital_changed(
        self,
        *,
        account_id: UUID,
        cash: Decimal,
        margin_used: Decimal,
        equity: Decimal,
        available_capital: Decimal,
        reason: CapitalAdjustmentReason,
        occurred_at: datetime | None = None,
        correlation_id: UUID,
        causation_id: UUID | None = None,
    ) -> DomainEvent:
        return self._publish(
            "portfolio.AccountCapitalChanged",
            payload={
                "account_id": str(account_id),
                "cash": self._fmt(cash),
                "margin_used": self._fmt(margin_used),
                "equity": self._fmt(equity),
                "available_capital": self._fmt(available_capital),
                "reason": reason.value,
                "occurred_at": (occurred_at or datetime.now(timezone.utc)).isoformat(),
            },
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

    def publish_exposure_changed(
        self,
        *,
        account_id: UUID,
        exposure: Decimal,
        occurred_at: datetime | None = None,
        correlation_id: UUID,
        causation_id: UUID | None = None,
    ) -> DomainEvent:
        return self._publish(
            "portfolio.ExposureChanged",
            payload={
                "account_id": str(account_id),
                "exposure": self._fmt(exposure),
                "occurred_at": (occurred_at or datetime.now(timezone.utc)).isoformat(),
            },
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _publish(
        self,
        event_type: str,
        *,
        payload: dict,
        correlation_id: UUID,
        causation_id: UUID | None = None,
    ) -> DomainEvent:
        event = DomainEvent.create(
            event_type=event_type,
            payload=payload,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
        self._bus.publish(event)
        return event
