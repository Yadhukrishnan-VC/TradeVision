from __future__ import annotations

from collections.abc import Callable

from apps.eventbus.application.ports import EventBus
from apps.eventbus.domain.events import DomainEvent
from apps.risk_management.infrastructure.tasks import evaluate_rule_firing


def handle_rule_fired(event: DomainEvent) -> None:
    """Dispatch a ``rule_engine.RuleFired`` event to the risk evaluator.

    ``causation_id`` is the RuleFired ``event_id``; the payload's
    ``analysis_event_id`` is the stable idempotency key consumed by the
    (analysis_event_id, rule_id) UniqueConstraint downstream. An optional
    ``account_id`` (set by backtest replay) is threaded through so the risk
    evaluation and the resulting approval target the run's isolated account.
    """
    data = event.payload
    evaluate_rule_firing.delay(
        symbol=data.get("symbol", ""),
        rule_id=data.get("rule_id", ""),
        event_type=data.get("event_type", ""),
        trigger_data=data.get("trigger_data", {}) or {},
        analysis_event_id=data.get("analysis_event_id", ""),
        occurred_at=data.get("occurred_at", ""),
        rule_fired_event_id=str(event.event_id),
        account_id=str(data.get("account_id", "")) or "",
    )


def handle_risk_approved(event: DomainEvent) -> None:
    """Dispatch a ``risk_management.RiskApproved`` event to the executor.

    The execution intake task is idempotent on ``risk_approved_event_id``
    (the RiskApproved ``event_id``), so redelivered approvals produce at
    most one ExecutionRequest / Order. Correlation/causation IDs travel
    through to the order lifecycle so the full chain stays traceable.
    """
    from apps.execution.infrastructure.tasks import handle_risk_approved as enqueue

    enqueue.delay(
        payload=dict(event.payload),
        correlation_id=str(event.correlation_id),
        causation_id=str(event.causation_id) if event.causation_id else "",
        risk_approved_event_id=str(event.event_id),
    )


SUBSCRIBED_EVENTS: dict[str, list[Callable[[DomainEvent], None]]] = {
    "rule_engine.RuleFired": [handle_rule_fired],
    "risk_management.RiskApproved": [handle_risk_approved],
}


def register_handlers(event_bus: EventBus) -> None:
    for event_type, handlers in SUBSCRIBED_EVENTS.items():
        for handler in handlers:
            event_bus.subscribe(
                event_type=event_type,
                handler=handler,
                consumer_group="risk_management",
            )
