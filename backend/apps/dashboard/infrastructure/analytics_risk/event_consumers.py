from __future__ import annotations

from collections.abc import Callable

from apps.dashboard.application.analytics_risk.projectors import (
    PnLSnapshotProjector,
    PerformanceRollupProjector,
    RiskMetricProjector,
)
from apps.eventbus.application.ports import EventBus
from apps.eventbus.domain.events import DomainEvent

SUBSCRIBED_EVENTS: dict[str, list[Callable[[DomainEvent], None]]] = {
    "marketdata.PriceTick": [
        PnLSnapshotProjector().handle,
    ],
    "positions.PositionOpened": [
        RiskMetricProjector().handle,
    ],
    "risk.AlertRaised": [
        RiskMetricProjector().handle,
    ],
    "risk.AlertResolved": [
        RiskMetricProjector().handle,
    ],
}


def register_handlers(event_bus: EventBus) -> None:
    for event_type, handlers in SUBSCRIBED_EVENTS.items():
        for handler in handlers:
            event_bus.subscribe(
                event_type=event_type,
                handler=handler,
                consumer_group="dashboard_analytics_risk",
            )

    event_bus.subscribe(
        event_type="positions.PositionQuantityChanged",
        handler=PnLSnapshotProjector().handle,
        consumer_group="dashboard_analytics_risk_pnl",
    )
    event_bus.subscribe(
        event_type="positions.PositionClosed",
        handler=PnLSnapshotProjector().handle,
        consumer_group="dashboard_analytics_risk_pnl",
    )
    event_bus.subscribe(
        event_type="positions.PositionQuantityChanged",
        handler=RiskMetricProjector().handle,
        consumer_group="dashboard_analytics_risk_risk",
    )
    event_bus.subscribe(
        event_type="positions.PositionClosed",
        handler=RiskMetricProjector().handle,
        consumer_group="dashboard_analytics_risk_risk",
    )

    from apps.dashboard.projection.internal_events import subscribe_internal

    subscribe_internal("trade_record_projected", PerformanceRollupProjector().handle_internal)
