from __future__ import annotations

from apps.common.domain.exceptions import DomainError


class EventBusError(DomainError):
    """Base exception for event bus failures."""


class EventPublishError(EventBusError):
    """Raised when publishing an event to the transport fails."""


class EventHandlerNotFoundError(EventBusError):
    """Raised when no handler is registered for an event type."""


class DeadLetterEventError(EventBusError):
    """Raised when an event exceeds its retry limit and is dead-lettered."""
