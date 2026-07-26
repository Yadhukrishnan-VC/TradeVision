from __future__ import annotations

from apps.common.domain.exceptions import DomainError, ValidationError


class InvalidSignatureError(ValidationError):
    """Raised when a webhook request has an invalid or missing signature.

    This can indicate a misconfiguration, a replay attempt, or an
    unauthorised caller.
    """


class MalformedPayloadError(ValidationError):
    """Raised when a webhook payload cannot be parsed or is missing
    required fields.
    """
