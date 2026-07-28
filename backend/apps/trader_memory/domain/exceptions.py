from __future__ import annotations

from apps.common.domain.exceptions import DomainError


class MemoryEntryNotFound(DomainError):
    pass


class DuplicateMemoryEntry(DomainError):
    pass
