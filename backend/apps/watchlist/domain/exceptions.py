from __future__ import annotations

from apps.common.domain.exceptions import DomainError, NotFoundError


class WatchlistError(DomainError):
    """Base exception for watchlist domain violations."""


class WatchlistEntryNotFoundError(WatchlistError):
    """Raised when a reorder references an entry not on the watchlist."""


class InstrumentNotFoundError(WatchlistError, NotFoundError):
    """Raised when adding an entry for an unknown instrument."""
