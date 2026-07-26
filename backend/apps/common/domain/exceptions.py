from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Base exception for all domain-level errors in the system."""

    def __init__(self, message: str = "", code: str | None = None, details: dict[str, Any] | None = None) -> None:
        self.code = code
        self.details = details or {}
        super().__init__(message)

    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.code:
            parts.append(f"[{self.code}]")
        return " ".join(parts)


class ValidationError(DomainError):
    """Raised when input validation fails."""


class ConcurrencyError(DomainError):
    """Raised when a concurrent modification is detected."""


class ExternalServiceError(DomainError):
    """Raised when an external service call fails."""


class NotFoundError(DomainError):
    """Raised when a requested resource is not found."""


class PermissionDeniedError(DomainError):
    """Raised when the actor lacks permission for an operation."""
