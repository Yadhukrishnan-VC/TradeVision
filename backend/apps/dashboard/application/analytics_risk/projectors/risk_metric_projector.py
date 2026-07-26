from __future__ import annotations

import uuid
from decimal import Decimal

from django.db.models import Max, Sum
from django.utils import timezone

from apps.dashboard.domain.analytics_risk.entities import RiskMetricSnapshot, RiskAlertProjection
from apps.dashboard.infrastructure.analytics_risk.models import (
    RiskMetricSnapshot as RiskMetricSnapshotModel,
)
from apps.dashboard.infrastructure.analytics_risk.models import RiskAlertProjection as RiskAlertProjectionModel
from apps.dashboard.infrastructure.trading_core.models import Holding
from apps.dashboard.projection.base import BaseProjectionService
from apps.eventbus.domain.events import DomainEvent


class RiskMetricProjector(BaseProjectionService):
    name = "risk_metric_projector"

    def _apply(self, event: DomainEvent) -> None:
        if event.event_type == "positions.PositionOpened":
            self._recompute_exposure(event)
        elif event.event_type == "positions.PositionQuantityChanged":
            self._recompute_exposure(event)
        elif event.event_type == "positions.PositionClosed":
            self._recompute_exposure(event)
        elif event.event_type == "risk.AlertRaised":
            self._apply_alert_raised(event)
        elif event.event_type == "risk.AlertResolved":
            self._apply_alert_resolved(event)

    def _recompute_exposure(self, event: DomainEvent) -> None:
        account_id = self._get_account_id(event)

        holdings = Holding.objects.filter(account_id=account_id)

        total_exposure = Decimal("0")
        largest_position_value = Decimal("0")
        sector_values: dict[str, Decimal] = {}
        total_notional = Decimal("0")

        for h in holdings:
            quantity = Decimal(str(h.quantity))
            entry = Decimal(str(h.entry_price))
            current = Decimal(str(h.current_price or h.entry_price))
            position_value = quantity * current
            total_exposure += position_value
            notional = quantity * entry
            total_notional += notional

            if position_value > largest_position_value:
                largest_position_value = position_value

            sector = getattr(h, "sector", "unknown")
            sector_values[sector] = sector_values.get(sector, Decimal("0")) + position_value

        largest_position_pct = Decimal("0")
        if total_exposure > Decimal("0"):
            largest_position_pct = (largest_position_value / total_exposure) * Decimal("100")

        sector_concentration_pct = Decimal("0")
        if sector_values and total_exposure > Decimal("0"):
            top_sector = max(sector_values.values())
            sector_concentration_pct = (top_sector / total_exposure) * Decimal("100")

        leverage_ratio = Decimal("1")
        if total_notional > Decimal("0") and total_exposure > Decimal("0"):
            leverage_ratio = total_exposure / total_notional
        if leverage_ratio < Decimal("1"):
            leverage_ratio = Decimal("1")

        snapshot = RiskMetricSnapshot(
            account_id=account_id,
            snapshot_at=timezone.now(),
            total_exposure=total_exposure,
            largest_position_pct=largest_position_pct,
            sector_concentration_pct=sector_concentration_pct,
            leverage_ratio=leverage_ratio,
        )

        row = RiskMetricSnapshotModel(
            id=uuid.uuid4(),
            account_id=snapshot.account_id,
            snapshot_at=snapshot.snapshot_at,
            total_exposure=snapshot.total_exposure,
            largest_position_pct=snapshot.largest_position_pct,
            sector_concentration_pct=snapshot.sector_concentration_pct,
            leverage_ratio=snapshot.leverage_ratio,
        )
        self._update_projection_metadata(row, event)
        row.save()

    def _apply_alert_raised(self, event: DomainEvent) -> None:
        payload = event.payload
        alert_id = payload.get("alert_id")
        if alert_id is None:
            return

        account_id = self._get_account_id(event)

        RiskAlertProjectionModel.objects.update_or_create(
            alert_id=alert_id,
            defaults={
                "account_id": account_id,
                "alert_type": payload.get("alert_type", "unknown"),
                "severity": payload.get("severity", "low"),
                "message": payload.get("message", ""),
                "raised_at": payload.get("raised_at", timezone.now()),
                "resolved_at": payload.get("resolved_at"),
                "last_event_id": event.event_id,
            },
        )

    def _apply_alert_resolved(self, event: DomainEvent) -> None:
        payload = event.payload
        alert_id = payload.get("alert_id")
        if alert_id is None:
            return

        try:
            alert = RiskAlertProjectionModel.objects.get(alert_id=alert_id)
        except RiskAlertProjectionModel.DoesNotExist:
            return

        alert.resolved_at = payload.get("resolved_at", timezone.now())
        alert.last_event_id = event.event_id
        alert.save()
