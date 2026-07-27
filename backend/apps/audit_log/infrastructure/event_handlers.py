from __future__ import annotations

from collections.abc import Callable

from apps.audit_log.services import AuditLogger
from apps.eventbus.application.ports import EventBus
from apps.eventbus.domain.events import DomainEvent


def register_handlers(event_bus: EventBus) -> None:
    logger = AuditLogger()
    event_bus.subscribe(
        event_type="*",
        handler=logger.log_event,
        consumer_group="audit_log",
    )
