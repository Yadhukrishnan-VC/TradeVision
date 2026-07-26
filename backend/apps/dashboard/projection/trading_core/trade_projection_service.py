from __future__ import annotations

import uuid
from decimal import Decimal

from django.utils import timezone

from apps.dashboard.infrastructure.trading_core.models import TradeRecord
from apps.dashboard.projection.base import BaseProjectionService
from apps.dashboard.projection.internal_events import DashboardInternalEvent, publish_internal
from apps.eventbus.domain.events import DomainEvent


class TradeProjectionService(BaseProjectionService):
    name = "trade_projector"

    def _apply(self, event: DomainEvent) -> None:
        if event.event_type == "positions.PositionClosed":
            self._apply_position_closed(event)

    def _apply_position_closed(self, event: DomainEvent) -> None:
        payload = event.payload
        account_id = self._get_account_id(event)

        opened_at_str = payload.get("opened_at", "")
        closed_at = timezone.now()

        entry_price = Decimal(str(payload.get("entry_price", 0)))
        exit_price = Decimal(str(payload.get("exit_price", 0)))
        quantity = Decimal(str(payload.get("quantity", 0)))
        realized_pnl = Decimal(str(payload.get("realized_pnl", 0)))
        realized_pnl_pct = Decimal(str(payload.get("realized_pnl_pct", 0)))

        holding_period_seconds = int(payload.get("holding_period_seconds", 0))

        trade = TradeRecord(
            trade_id=uuid.uuid4(),
            account_id=account_id,
            symbol=payload["symbol"],
            side=payload.get("side", "LONG"),
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=quantity,
            realized_pnl=realized_pnl,
            realized_pnl_pct=realized_pnl_pct,
            opened_at=timezone.now(),
            closed_at=closed_at,
            holding_period_seconds=holding_period_seconds,
        )
        self._update_projection_metadata(trade, event)
        trade.save()

        self._fire_projected_event(trade, event)

    def _fire_projected_event(self, trade: TradeRecord, event: DomainEvent) -> None:
        internal_event = DashboardInternalEvent.create(
            event_type="trade_record_projected",
            payload={
                "account_id": str(trade.account_id),
                "trade_id": str(trade.trade_id),
                "symbol": trade.symbol,
                "closed_at": trade.closed_at.isoformat(),
            },
            source_event_id=event.event_id,
        )
        publish_internal(internal_event)
