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


def _group_slug(instance: object) -> str:
    """Stable, lowercase consumer-group suffix for a bound projection handler."""
    name = type(instance).__name__
    if name.endswith("ProjectionService"):
        name = name[: -len("ProjectionService")]
    return "".join(
        f"_{char.lower()}" if char.isupper() else char for char in name
    ).lstrip("_")


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
    "rule_engine.RuleFired": [
        PortfolioSummaryProjectionService().handle,
    ],
    "ai_engine.RecommendationIssued": [
        PortfolioSummaryProjectionService().handle,
    ],
    "recommendations.RecommendationCreated": [
        PortfolioSummaryProjectionService().handle,
    ],
}


def register_handlers(event_bus: EventBus) -> None:
    """Subscribe each projection under its own consumer group.

    Each projection service is an independent consumer with its own
    ``ProcessedEvent`` dedup key, so they must not share a group: Redis
    delivers a stream entry to exactly one member of a consumer group, which
    would starve whichever projection lost the race (a silently stale
    dashboard). The group name is derived per handler for that reason.
    """
    for event_type, handlers in SUBSCRIBED_EVENTS.items():
        for handler in handlers:
            instance = handler.__self__
            event_bus.subscribe(
                event_type=event_type,
                handler=handler,
                consumer_group=f"dashboard_trading_core_{_group_slug(instance)}",
            )
