from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from django.db import transaction

from core.services import BaseService
from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.recommendations.domain.entities import RecommendationAggregate, RecommendationStatus
from apps.recommendations.domain.exceptions import IllegalTransition, RecommendationNotFound
from apps.recommendations.infrastructure.models import Recommendation, RecommendationStatusHistory
from apps.recommendations.infrastructure.repositories import RecommendationRepository


class RecommendationCommandService(BaseService):
    def __init__(self) -> None:
        super().__init__()
        self._repository = RecommendationRepository()

    def create_from_ai_response(
        self,
        symbol: str,
        direction: str,
        confidence_score: Decimal,
        analysis_event_id: uuid.UUID | None = None,
        rule_execution_id: uuid.UUID | None = None,
        strategy_id: uuid.UUID | None = None,
        confidence_evaluation_id: uuid.UUID | None = None,
        provider: str = "fallback",
        correlation_id: uuid.UUID | None = None,
    ) -> RecommendationAggregate:
        recommendation = Recommendation(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
            status=RecommendationStatus.DRAFT,
            analysis_event_id=analysis_event_id,
            rule_execution_id=rule_execution_id,
            strategy_id=strategy_id,
            confidence_evaluation_id=confidence_evaluation_id,
            provider=provider,
            correlation_id=correlation_id,
        )
        with transaction.atomic():
            recommendation.full_clean()
            recommendation.save()

            aggregate = self._to_aggregate(recommendation)
        self._publish_created(aggregate)
        return aggregate

    def publish_recommendation(self, recommendation_id: uuid.UUID) -> RecommendationAggregate:
        rec = self._repository.get_by_id(recommendation_id)
        if rec is None:
            raise RecommendationNotFound(f"Recommendation {recommendation_id} not found")

        aggregate = self._to_aggregate(rec)
        aggregate.publish()

        with transaction.atomic():
            _update_from_aggregate(rec, aggregate)
            rec.save()
            self._record_status_history(rec, RecommendationStatus.DRAFT, RecommendationStatus.PUBLISHED, "auto-publish", "system")
        self._publish_status_changed(rec, RecommendationStatus.DRAFT, RecommendationStatus.PUBLISHED)
        return aggregate

    def accept_recommendation(
        self, recommendation_id: uuid.UUID, reason: str = "", changed_by: str = "user"
    ) -> RecommendationAggregate:
        return self._transition(
            recommendation_id, RecommendationStatus.ACCEPTED, reason, changed_by
        )

    def reject_recommendation(
        self, recommendation_id: uuid.UUID, reason: str = "", changed_by: str = "user"
    ) -> RecommendationAggregate:
        return self._transition(
            recommendation_id, RecommendationStatus.REJECTED, reason, changed_by
        )

    def expire_recommendation(
        self, recommendation_id: uuid.UUID, reason: str = "timeout"
    ) -> RecommendationAggregate:
        return self._transition(
            recommendation_id, RecommendationStatus.EXPIRED, reason, "system"
        )

    def _transition(
        self, recommendation_id: uuid.UUID, target: str, reason: str, changed_by: str
    ) -> RecommendationAggregate:
        rec = self._repository.get_by_id(recommendation_id)
        if rec is None:
            raise RecommendationNotFound(f"Recommendation {recommendation_id} not found")

        from_status = rec.status
        aggregate = self._to_aggregate(rec)

        if target == RecommendationStatus.ACCEPTED:
            aggregate.accept()
        elif target == RecommendationStatus.REJECTED:
            aggregate.reject()
        elif target == RecommendationStatus.EXPIRED:
            aggregate.expire()
        else:
            raise IllegalTransition(f"Cannot transition to {target}")

        with transaction.atomic():
            _update_from_aggregate(rec, aggregate)
            rec.save()
            self._record_status_history(rec, from_status, target, reason, changed_by)
        self._publish_status_changed(rec, from_status, target)
        return aggregate

    def _record_status_history(
        self, rec: Recommendation, from_status: str, to_status: str, reason: str, changed_by: str
    ) -> None:
        RecommendationStatusHistory.objects.create(
            recommendation=rec,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            changed_by=changed_by,
        )

    def _publish_created(self, aggregate: RecommendationAggregate) -> None:
        event = DomainEvent.create(
            event_type="recommendations.RecommendationCreated",
            payload={
                "recommendation_id": str(aggregate.id),
                "symbol": aggregate.symbol,
                "direction": aggregate.direction,
                "confidence_score": str(aggregate.confidence_score),
                "status": aggregate.status,
                "strategy_id": str(aggregate.strategy_id) if aggregate.strategy_id else None,
            },
            correlation_id=aggregate.id,
        )
        try:
            get_event_bus().publish(event)
        except Exception:
            self._logger.exception(
                "Failed to publish RecommendationCreated",
                extra={"recommendation_id": str(aggregate.id)},
            )

    def _publish_status_changed(
        self, rec: Recommendation, from_status: str, to_status: str
    ) -> None:
        event = DomainEvent.create(
            event_type="recommendations.RecommendationStatusChanged",
            payload={
                "recommendation_id": str(rec.id),
                "from_status": from_status,
                "to_status": to_status,
                "reason": "",
                "changed_by": "system",
            },
            correlation_id=rec.id,
        )
        try:
            get_event_bus().publish(event)
        except Exception:
            self._logger.exception(
                "Failed to publish RecommendationStatusChanged",
                extra={"recommendation_id": str(rec.id)},
            )

    def _to_aggregate(self, rec: Recommendation) -> RecommendationAggregate:
        return RecommendationAggregate(
            id=rec.id,
            symbol=rec.symbol,
            direction=rec.direction,
            confidence_score=rec.confidence_score,
            status=rec.status,
            analysis_event_id=rec.analysis_event_id,
            rule_execution_id=rec.rule_execution_id if rec.rule_execution_id else None,
            strategy_id=rec.strategy_id,
            confidence_evaluation_id=rec.confidence_evaluation_id,
            provider=rec.provider,
            correlation_id=rec.correlation_id,
            published_at=rec.published_at,
            created_at=rec.created_at,
        )


def _update_from_aggregate(rec: Recommendation, aggregate: RecommendationAggregate) -> None:
    rec.status = aggregate.status
    rec.published_at = aggregate.published_at
