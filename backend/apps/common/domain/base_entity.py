from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.eventbus.domain.events import DomainEvent


class BaseEntity:
    """Base class for all domain entities across the system.

    Provides a uniform identity (UUID), created/updated timestamps, and
    an event-collection mechanism so application services can defer event
    publishing until after a successful transaction commit.
    """

    def __init__(self, id: uuid.UUID | None = None) -> None:
        self._id: uuid.UUID = id or uuid.uuid4()
        self._created_at: datetime = datetime.now(timezone.utc)
        self._updated_at: datetime = datetime.now(timezone.utc)
        self._pending_events: list[DomainEvent] = []

    @property
    def id(self) -> uuid.UUID:
        return self._id

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    def register_event(self, event: DomainEvent) -> None:
        """Register a domain event to be published after the current transaction commits.

        Args:
            event: The domain event to register.

        Raises:
            TypeError: If event is not a DomainEvent instance.
        """
        self._pending_events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        """Drain and return all pending domain events.

        Returns:
            A list of all pending DomainEvent instances. The internal
            pending-events list is cleared after this call.
        """
        events = list(self._pending_events)
        self._pending_events.clear()
        return events

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, BaseEntity):
            return NotImplemented
        return self._id == other._id

    def __hash__(self) -> int:
        return hash(self._id)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self._id!r})"
