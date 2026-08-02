from __future__ import annotations

from apps.common.domain.exceptions import DomainError


class RiskEvaluationError(DomainError):
    """Raised when a risk decision cannot be produced or published."""


class RiskConfigNotFound(DomainError):
    pass


class RiskConfigConflict(DomainError):
    pass
