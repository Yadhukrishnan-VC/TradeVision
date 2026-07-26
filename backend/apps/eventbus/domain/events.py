from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class DomainEvent:
    """Base domain event as defined by the architecture's event schema.

    Every event flowing through the system is an instance of this
    dataclass. It carries the standard envelope fields plus an
    opaque payload dictionary whose shape is determined by the
    specific event type.
    """

    event_id: uuid.UUID
    event_type: str
    occurred_at: datetime
    payload: dict[str, Any]
    version: int
    correlation_id: uuid.UUID
    causation_id: uuid.UUID | None = None

    @classmethod
    def create(
        cls,
        event_type: str,
        payload: dict[str, Any],
        correlation_id: uuid.UUID,
        causation_id: uuid.UUID | None = None,
        version: int = 1,
    ) -> DomainEvent:
        """Factory method that auto-generates event_id and occurred_at.

        Args:
            event_type: A dot-separated string identifying the event
                (e.g. ``accounts.UserLoggedIn``).
            payload: The event-specific data payload.
            correlation_id: UUID tracing this event to the original
                request or command that caused it.
            causation_id: UUID of the event that caused this event
                (if applicable).
            version: Schema version number (default 1).

        Returns:
            A fully populated DomainEvent instance.
        """
        return cls(
            event_id=uuid.uuid4(),
            event_type=event_type,
            occurred_at=datetime.now(timezone.utc),
            payload=payload,
            version=version,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
