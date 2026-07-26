from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.dashboard.infrastructure.common.event_log import EventLog
from apps.eventbus.domain.events import DomainEvent

logger = logging.getLogger(__name__)


class BaseProjectionService(ABC):
    name: str

    @abstractmethod
    def _apply(self, event: DomainEvent) -> None:
        ...

    def handle(self, event: DomainEvent) -> None:
        if EventLog.objects.has_been_applied(event.event_id, self.name):
            logger.debug(
                "Event already applied, skipping",
                extra={
                    "projector": self.name,
                    "event_id": str(event.event_id),
                    "event_type": event.event_type,
                },
            )
            return

        with transaction.atomic():
            self._apply(event)
            EventLog.objects.mark_applied(event.event_id, self.name)

        logger.info(
            "Projection applied",
            extra={
                "projector": self.name,
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "correlation_id": str(event.correlation_id),
            },
        )

    def _update_projection_metadata(
        self, instance: Any, event: DomainEvent, field_map: dict[str, str] | None = None
    ) -> None:
        now = timezone.now()
        instance.projection_version += 1
        instance.projection_updated_at = now
        instance.last_event_id = event.event_id
        instance.last_event_version = event.version

    def _get_account_id(self, event: DomainEvent) -> UUID:
        return UUID(event.payload["account_id"])
