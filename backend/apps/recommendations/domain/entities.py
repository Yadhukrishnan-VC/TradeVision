from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from apps.recommendations.domain.exceptions import IllegalTransition


class RecommendationStatus:
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

    VALID_TRANSITIONS = {
        DRAFT: [PUBLISHED],
        PUBLISHED: [ACCEPTED, REJECTED, EXPIRED],
        ACCEPTED: [],
        REJECTED: [],
        EXPIRED: [],
    }

    CHOICES = [
        (DRAFT, "Draft"),
        (PUBLISHED, "Published"),
        (ACCEPTED, "Accepted"),
        (REJECTED, "Rejected"),
        (EXPIRED, "Expired"),
    ]


@dataclass
class RecommendationAggregate:
    id: UUID
    symbol: str
    direction: str
    confidence_score: Decimal
    status: str
    analysis_event_id: UUID | None
    rule_execution_id: UUID | None
    strategy_id: UUID | None
    confidence_evaluation_id: UUID | None
    published_at: datetime | None
    created_at: datetime | None = None

    def publish(self) -> None:
        self._transition(RecommendationStatus.PUBLISHED)
        from datetime import datetime, timezone
        self.published_at = datetime.now(timezone.utc)

    def accept(self) -> None:
        self._transition(RecommendationStatus.ACCEPTED)

    def reject(self) -> None:
        self._transition(RecommendationStatus.REJECTED)

    def expire(self) -> None:
        self._transition(RecommendationStatus.EXPIRED)

    def _transition(self, target: str) -> None:
        allowed = RecommendationStatus.VALID_TRANSITIONS.get(self.status, [])
        if target not in allowed:
            raise IllegalTransition(
                f"Cannot transition from {self.status} to {target}"
            )
        self.status = target
