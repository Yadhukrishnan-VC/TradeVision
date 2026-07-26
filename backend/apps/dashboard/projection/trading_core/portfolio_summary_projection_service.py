from __future__ import annotations

import uuid
from decimal import Decimal

from apps.dashboard.infrastructure.trading_core.cache import DashboardHomeCache
from apps.dashboard.infrastructure.trading_core.models import DashboardHomeSummary
from apps.dashboard.projection.base import BaseProjectionService
from apps.eventbus.domain.events import DomainEvent


class PortfolioSummaryProjectionService(BaseProjectionService):
    name = "portfolio_summary_projector"

    def __init__(self) -> None:
        self._cache = DashboardHomeCache()

    def _apply(self, event: DomainEvent) -> None:
        event_type = event.event_type
        account_id = self._get_account_id(event)

        if event_type == "positions.PositionOpened":
            self._increment_open_positions(account_id, event)
        elif event_type == "positions.PositionClosed":
            self._decrement_open_positions(account_id, event)
        elif event_type == "orders.OrderPlaced":
            self._increment_open_orders(account_id, event)
        elif event_type in ("orders.OrderFilled", "orders.OrderCancelled", "orders.OrderRejected", "orders.OrderExpired"):
            self._decrement_open_orders(account_id, event)
        elif event_type == "risk.AlertRaised":
            self._increment_alerts(account_id, event)
        elif event_type == "risk.AlertResolved":
            self._decrement_alerts(account_id, event)
        elif event_type == "broker.ConnectionStatusChanged":
            self._update_broker_status(account_id, event)
        elif event_type == "marketdata.SessionStatusChanged":
            self._update_market_session_status(account_id, event)
        elif event_type == "analytics.PnLSnapshotUpdated":
            self._update_pnl(account_id, event)

    def _get_or_create_summary(self, account_id: uuid.UUID) -> DashboardHomeSummary:
        summary, created = DashboardHomeSummary.objects.get_or_create(pk=account_id)
        return summary

    def _increment_open_positions(self, account_id: uuid.UUID, event: DomainEvent) -> None:
        summary = self._get_or_create_summary(account_id)
        summary.open_positions_count += 1
        self._update_projection_metadata(summary, event)
        summary.save()
        self._invalidate_cache(account_id)

    def _decrement_open_positions(self, account_id: uuid.UUID, event: DomainEvent) -> None:
        summary = self._get_or_create_summary(account_id)
        summary.open_positions_count = max(0, summary.open_positions_count - 1)
        self._update_projection_metadata(summary, event)
        summary.save()
        self._invalidate_cache(account_id)

    def _increment_open_orders(self, account_id: uuid.UUID, event: DomainEvent) -> None:
        summary = self._get_or_create_summary(account_id)
        summary.open_orders_count += 1
        self._update_projection_metadata(summary, event)
        summary.save()
        self._invalidate_cache(account_id)

    def _decrement_open_orders(self, account_id: uuid.UUID, event: DomainEvent) -> None:
        summary = self._get_or_create_summary(account_id)
        summary.open_orders_count = max(0, summary.open_orders_count - 1)
        self._update_projection_metadata(summary, event)
        summary.save()
        self._invalidate_cache(account_id)

    def _increment_alerts(self, account_id: uuid.UUID, event: DomainEvent) -> None:
        summary = self._get_or_create_summary(account_id)
        summary.active_alerts_count += 1
        self._update_projection_metadata(summary, event)
        summary.save()
        self._invalidate_cache(account_id)

    def _decrement_alerts(self, account_id: uuid.UUID, event: DomainEvent) -> None:
        summary = self._get_or_create_summary(account_id)
        summary.active_alerts_count = max(0, summary.active_alerts_count - 1)
        self._update_projection_metadata(summary, event)
        summary.save()
        self._invalidate_cache(account_id)

    def _update_broker_status(self, account_id: uuid.UUID, event: DomainEvent) -> None:
        payload = event.payload
        summary = self._get_or_create_summary(account_id)
        summary.broker_connection_status = payload.get("status", summary.broker_connection_status)
        self._update_projection_metadata(summary, event)
        summary.save()
        self._invalidate_cache(account_id)

    def _update_market_session_status(self, account_id: uuid.UUID, event: DomainEvent) -> None:
        payload = event.payload
        summary = self._get_or_create_summary(account_id)
        summary.market_session_status = payload.get("status", summary.market_session_status)
        self._update_projection_metadata(summary, event)
        summary.save()
        self._invalidate_cache(account_id)

    def _update_pnl(self, account_id: uuid.UUID, event: DomainEvent) -> None:
        payload = event.payload
        summary = self._get_or_create_summary(account_id)
        if "realized_pnl" in payload:
            summary.today_realized_pnl = Decimal(str(payload["realized_pnl"]))
        if "unrealized_pnl" in payload:
            summary.today_unrealized_pnl = Decimal(str(payload["unrealized_pnl"]))
        self._update_projection_metadata(summary, event)
        summary.save()
        self._invalidate_cache(account_id)

    def _invalidate_cache(self, account_id: uuid.UUID) -> None:
        try:
            self._cache.delete_summary(account_id)
        except Exception:
            pass
