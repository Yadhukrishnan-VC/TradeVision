from __future__ import annotations

from apps.common.domain.exceptions import DomainError, NotFoundError, ValidationError


class PositionNotFound(NotFoundError):
    pass


class OrderNotFound(NotFoundError):
    pass


class TradeRecordNotFound(NotFoundError):
    pass


class HoldingNotFound(NotFoundError):
    pass


class AccountSummaryNotInitialized(NotFoundError):
    pass


class PortfolioNotInitialized(NotFoundError):
    pass


class OrderProjectionConflict(DomainError):
    pass


class TradeProjectionConflict(DomainError):
    pass


class InvalidEventPayload(ValidationError):
    pass


class EventOutOfOrder(DomainError):
    pass
