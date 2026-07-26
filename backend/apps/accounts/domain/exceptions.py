from __future__ import annotations

from apps.common.domain.exceptions import DomainError, ValidationError


class InvalidRoleError(ValidationError):
    """Raised when an invalid or unsupported role is used."""


class InvalidScopeError(ValidationError):
    """Raised when an invalid or unknown scope value is provided."""


class ExpiredAPIKeyError(DomainError):
    """Raised when an expired API key is used for authentication."""


class RevokedAPIKeyError(DomainError):
    """Raised when a revoked API key is used for authentication."""


class InvalidTokenError(DomainError):
    """Raised when a JWT token is invalid, expired, or malformed."""
