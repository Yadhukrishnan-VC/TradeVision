from __future__ import annotations

from apps.common.domain.exceptions import DomainError


class ReplayError(DomainError):
    """Raised when the replay operation fails."""


class NoEventsToReplay(DomainError):
    """Raised when no events match the replay criteria."""
