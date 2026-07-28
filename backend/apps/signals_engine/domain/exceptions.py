from __future__ import annotations

from apps.common.domain.exceptions import ValidationError


class InvalidSignalPayloadError(ValidationError):
    """Raised when a signal payload is malformed or missing required fields."""
