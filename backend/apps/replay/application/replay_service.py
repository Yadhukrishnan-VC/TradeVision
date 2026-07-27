from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.eventbus.infrastructure.models import ProcessedEvent, StoredEvent

logger = logging.getLogger(__name__)


class ReplayService:
    @staticmethod
    def replay(
        correlation_id: UUID | None = None,
        time_range: tuple[datetime, datetime] | None = None,
        target_consumer_group: str = "journal",
    ) -> int:
        qs = StoredEvent.objects.all()

        if correlation_id:
            qs = qs.filter(correlation_id=correlation_id)
        if time_range:
            qs = qs.filter(
                occurred_at__gte=time_range[0],
                occurred_at__lte=time_range[1],
            )

        bus = get_event_bus()
        count = 0

        for stored in qs.order_by("occurred_at").iterator():
            if ProcessedEvent.objects.filter(
                event_id=stored.event_id,
                consumer_group=target_consumer_group,
            ).exists():
                continue

            event = DomainEvent(
                event_id=stored.event_id,
                event_type=stored.event_type,
                occurred_at=stored.occurred_at,
                payload=stored.payload,
                version=stored.version,
                correlation_id=stored.correlation_id,
                causation_id=stored.causation_id,
            )

            try:
                bus.publish(event)
                count += 1
            except Exception:
                logger.exception(
                    "Failed to replay event",
                    extra={
                        "event_id": str(stored.event_id),
                        "event_type": stored.event_type,
                        "consumer_group": target_consumer_group,
                    },
                )

        logger.info(
            "Replay completed",
            extra={
                "correlation_id": str(correlation_id) if correlation_id else None,
                "consumer_group": target_consumer_group,
                "events_replayed": count,
            },
        )

        return count
