from __future__ import annotations

from apps.common.domain.exceptions import DomainError


class IllegalTransition(DomainError):
    pass


class RecommendationNotFound(DomainError):
    pass
