from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class DashboardInternalEvent:
    event_id: uuid.UUID
    event_type: str
    occurred_at: datetime
    payload: dict[str, Any]
    source_event_id: uuid.UUID

    @classmethod
    def create(
        cls,
        event_type: str,
        payload: dict[str, Any],
        source_event_id: uuid.UUID,
    ) -> DashboardInternalEvent:
        return cls(
            event_id=uuid.uuid4(),
            event_type=event_type,
            occurred_at=datetime.now(timezone.utc),
            payload=payload,
            source_event_id=source_event_id,
        )


_INTERNAL_HANDLERS: dict[str, list[callable]] = {}


def subscribe_internal(event_type: str, handler: callable) -> None:
    if event_type not in _INTERNAL_HANDLERS:
        _INTERNAL_HANDLERS[event_type] = []
    _INTERNAL_HANDLERS[event_type].append(handler)


def publish_internal(event: DashboardInternalEvent) -> None:
    handlers = _INTERNAL_HANDLERS.get(event.event_type, [])
    for handler in handlers:
        try:
            handler(event)
        except Exception:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(
                "Internal event handler failed",
                extra={
                    "event_type": event.event_type,
                    "handler": getattr(handler, "__name__", str(handler)),
                },
            )
