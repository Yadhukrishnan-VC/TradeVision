from __future__ import annotations

from apps.common.domain.exceptions import DomainError, ValidationError


class InvalidTimeframeError(ValidationError):
    pass


class DateRangeTooLargeError(ValidationError):
    pass


class InsufficientTradeDataError(DomainError):
    pass
