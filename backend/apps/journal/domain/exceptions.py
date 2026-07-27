from __future__ import annotations

from apps.common.domain.exceptions import DomainError


class JournalEntryNotFound(DomainError):
    """Raised when a journal entry cannot be found for a given correlation_id."""


class JournalEntryAlreadyFinalized(DomainError):
    """Raised when attempting to modify an already-finalized journal entry."""


class InvalidOutcomeError(DomainError):
    """Raised when an unsupported outcome value is provided."""
