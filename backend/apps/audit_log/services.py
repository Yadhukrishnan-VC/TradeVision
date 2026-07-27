from __future__ import annotations

import logging

from apps.eventbus.domain.events import DomainEvent

from apps.audit_log.infrastructure.models import AuditLogEntry

logger = logging.getLogger(__name__)


class AuditLogger:
    def log_event(self, event: DomainEvent) -> None:
        actor = self._determine_actor(event)
        AuditLogEntry.objects.create(
            actor=actor,
            action=event.event_type,
            target_type=event.event_type.split(".")[0] if "." in event.event_type else event.event_type,
            target_id=str(event.correlation_id),
            metadata=event.payload,
            occurred_at=event.occurred_at,
        )

    def _determine_actor(self, event: DomainEvent) -> str:
        if event.event_type.startswith("ai.") or event.event_type.startswith("recommendations."):
            return "ai"
        if event.event_type.startswith("accounts.") or event.event_type.startswith("user."):
            return "user"
        return "system"
