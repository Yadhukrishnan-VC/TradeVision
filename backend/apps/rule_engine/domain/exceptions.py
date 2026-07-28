from __future__ import annotations

from apps.common.domain.exceptions import DomainError


class RuleConfigNotFound(DomainError):
    pass


class RuleConfigConflict(DomainError):
    pass


class RuleEvaluationError(DomainError):
    pass
