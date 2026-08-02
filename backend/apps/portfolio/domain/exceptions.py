from __future__ import annotations

from apps.common.domain.exceptions import DomainError


class PortfolioDomainError(DomainError):
    """Base exception for portfolio domain violations.

    Mirrors ``rule_engine`` / ``risk_management`` domain exception modules:
    all portfolio domain failures descend from ``apps.common`` ``DomainError``
    so catch-all handlers keep working.
    """


class InsufficientCashError(PortfolioDomainError):
    """Raised when a withdrawal would exceed available cash."""


class InsufficientAvailableCapitalError(PortfolioDomainError):
    """Raised when reserving margin would exceed available capital."""


class InvalidFillError(PortfolioDomainError):
    """Raised when a fill carries an invalid quantity or price."""
