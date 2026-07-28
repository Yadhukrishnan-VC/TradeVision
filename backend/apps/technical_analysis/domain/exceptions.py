from __future__ import annotations

from apps.common.domain.exceptions import DomainError, ValidationError


class InvalidTechnicalAnalysisPayloadError(ValidationError):
    """Raised when a webhook payload fails validation."""


class MissingRequiredFieldError(InvalidTechnicalAnalysisPayloadError):
    """Raised when a required field is missing from the payload."""


class InvalidFieldValueError(InvalidTechnicalAnalysisPayloadError):
    """Raised when a field has an invalid value."""


class SnapshotPersistenceError(DomainError):
    """Raised when persisting a technical analysis snapshot fails."""
