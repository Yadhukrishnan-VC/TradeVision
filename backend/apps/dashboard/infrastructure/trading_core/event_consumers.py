from __future__ import annotations

from collections.abc import Callable

from apps.dashboard.projection.trading_core.order_projection_service import OrderProjectionService
from apps.dashboard.projection.trading_core.portfolio_summary_projection_service import (
    PortfolioSummaryProjectionService,
)
from apps.dashboard.projection.trading_core.position_projection_service import PositionProjectionService
from apps.dashboard.projection.trading_core.trade_projection_service import TradeProjectionService
from apps.eventbus.application.ports import EventBus
from apps.eventbus.domain.events import DomainEvent

SUBSCRIBED_EVENTS: dict[str, list[Callable[[DomainEvent], None]]] = {
    "positions.PositionOpened": [
        PositionProjectionService().handle,
        PortfolioSummaryProjectionService().handle,
    ],
    "positions.PositionQuantityChanged": [
        PositionProjectionService().handle,
    ],
    "positions.PositionClosed": [
        PositionProjectionService().handle,
        TradeProjectionService().handle,
        PortfolioSummaryProjectionService().handle,
    ],
    "orders.OrderPlaced": [
        OrderProjectionService().handle,
        PortfolioSummaryProjectionService().handle,
    ],
    "orders.OrderPartiallyFilled": [
        OrderProjectionService().handle,
    ],
    "orders.OrderFilled": [
        OrderProjectionService().handle,
        PortfolioSummaryProjectionService().handle,
    ],
    "orders.OrderCancelled": [
        OrderProjectionService().handle,
        PortfolioSummaryProjectionService().handle,
    ],
    "orders.OrderRejected": [
        OrderProjectionService().handle,
        PortfolioSummaryProjectionService().handle,
    ],
    "orders.OrderExpired": [
        OrderProjectionService().handle,
        PortfolioSummaryProjectionService().handle,
    ],
    "risk.AlertRaised": [
        PortfolioSummaryProjectionService().handle,
    ],
    "risk.AlertResolved": [
        PortfolioSummaryProjectionService().handle,
    ],
    "broker.ConnectionStatusChanged": [
        PortfolioSummaryProjectionService().handle,
    ],
    "marketdata.SessionStatusChanged": [
        PortfolioSummaryProjectionService().handle,
    ],
    "analytics.PnLSnapshotUpdated": [
        PortfolioSummaryProjectionService().handle,
    ],
}


def register_handlers(event_bus: EventBus) -> None:
    for event_type, handlers in SUBSCRIBED_EVENTS.items():
        for handler in handlers:
            event_bus.subscribe(
                event_type=event_type,
                handler=handler,
                consumer_group="dashboard_trading_core",
            )
