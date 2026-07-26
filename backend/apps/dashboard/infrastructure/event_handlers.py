from __future__ import annotations

from apps.eventbus.application.ports import EventBus


def register_handlers(event_bus: EventBus) -> None:
    from apps.dashboard.infrastructure.trading_core.event_consumers import register_handlers as register_trading_core
    register_trading_core(event_bus)

    from apps.dashboard.infrastructure.analytics_risk.event_consumers import register_handlers as register_analytics_risk
    register_analytics_risk(event_bus)
