from __future__ import annotations

from collections.abc import Callable

from apps.eventbus.application.ports import EventBus
from apps.eventbus.domain.events import DomainEvent
from apps.journal.application.journal_assembly_service import JournalAssemblyService

SUBSCRIBED_EVENTS: dict[str, list[Callable[[DomainEvent], None]]] = {
    "signals.SignalCreated": [JournalAssemblyService().handle],
    "decisions.TradeDecisionMade": [JournalAssemblyService().handle],
    "orders.OrderPlaced": [JournalAssemblyService().handle],
    "orders.OrderPartiallyFilled": [JournalAssemblyService().handle],
    "orders.OrderFilled": [JournalAssemblyService().handle],
    "orders.OrderCancelled": [JournalAssemblyService().handle],
    "orders.OrderRejected": [JournalAssemblyService().handle],
    "orders.OrderExpired": [JournalAssemblyService().handle],
    "positions.PositionOpened": [JournalAssemblyService().handle],
    "positions.PositionQuantityChanged": [JournalAssemblyService().handle],
    "positions.PositionClosed": [JournalAssemblyService().handle],
    "risk.AlertRaised": [JournalAssemblyService().handle],
    "risk.AlertResolved": [JournalAssemblyService().handle],
    "rule_engine.RuleFired": [JournalAssemblyService().handle],
    "ai_engine.RecommendationIssued": [JournalAssemblyService().handle],
    "recommendations.RecommendationCreated": [JournalAssemblyService().handle],
    "recommendations.RecommendationStatusChanged": [JournalAssemblyService().handle],
}


def register_handlers(event_bus: EventBus) -> None:
    for event_type, handlers in SUBSCRIBED_EVENTS.items():
        for handler in handlers:
            event_bus.subscribe(
                event_type=event_type,
                handler=handler,
                consumer_group="journal",
            )
