from __future__ import annotations

import uuid
from decimal import Decimal

from django.utils import timezone

from apps.dashboard.domain.analytics_risk.entities import PnLSnapshot
from apps.dashboard.infrastructure.analytics_risk.models import PnLSnapshot as PnLSnapshotModel
from apps.dashboard.projection.base import BaseProjectionService
from apps.eventbus.domain.events import DomainEvent


class PnLSnapshotProjector(BaseProjectionService):
    name = "pnl_snapshot_projector"

    def _apply(self, event: DomainEvent) -> None:
        if event.event_type == "positions.PositionQuantityChanged":
            self._apply_quantity_change(event)
        elif event.event_type == "positions.PositionClosed":
            self._apply_position_closed(event)
        elif event.event_type == "positions.PriceTick":
            self._apply_price_tick(event)

    def _apply_quantity_change(self, event: DomainEvent) -> None:
        self._compute_and_store(event)

    def _apply_position_closed(self, event: DomainEvent) -> None:
        self._compute_and_store(event)

    def _apply_price_tick(self, event: DomainEvent) -> None:
        self._compute_and_store(event)

    def _compute_and_store(self, event: DomainEvent) -> None:
        payload = event.payload
        account_id = self._get_account_id(event)

        realized = Decimal(str(payload.get("realized_pnl", 0)))
        unrealized = Decimal(str(payload.get("unrealized_pnl", 0)))
        total = realized + unrealized

        latest = PnLSnapshotModel.objects.filter(account_id=account_id).order_by("-snapshot_at").first()
        if latest:
            cumulative = Decimal(str(latest.cumulative_pnl)) + total
            peak = max(Decimal(str(latest.peak_cumulative_pnl)), cumulative)
        else:
            cumulative = total
            peak = total

        drawdown = Decimal("0")
        if peak > Decimal("0"):
            from_peak = peak - cumulative
            drawdown = (from_peak / peak) * Decimal("100")

        snapshot = PnLSnapshot(
            account_id=account_id,
            snapshot_at=timezone.now(),
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            total_pnl=total,
            cumulative_pnl=cumulative,
            peak_cumulative_pnl=peak,
            drawdown_pct=drawdown,
            last_event_id=event.event_id,
        )

        row = PnLSnapshotModel(
            id=uuid.uuid4(),
            account_id=snapshot.account_id,
            snapshot_at=snapshot.snapshot_at,
            realized_pnl=snapshot.realized_pnl,
            unrealized_pnl=snapshot.unrealized_pnl,
            total_pnl=snapshot.total_pnl,
            cumulative_pnl=snapshot.cumulative_pnl,
            peak_cumulative_pnl=snapshot.peak_cumulative_pnl,
            drawdown_pct=snapshot.drawdown_pct,
            last_event_id=snapshot.last_event_id,
        )
        self._update_projection_metadata(row, event)
        row.save()
