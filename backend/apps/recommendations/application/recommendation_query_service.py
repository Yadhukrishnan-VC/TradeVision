from __future__ import annotations

import uuid
from typing import Any

from core.services import BaseService
from apps.recommendations.domain.entities import RecommendationAggregate
from apps.recommendations.domain.exceptions import RecommendationNotFound
from apps.recommendations.infrastructure.models import Recommendation
from apps.recommendations.infrastructure.repositories import RecommendationRepository


class RecommendationQueryService(BaseService):
    def __init__(self) -> None:
        super().__init__()
        self._repository = RecommendationRepository()

    def get_recommendation(self, recommendation_id: uuid.UUID) -> RecommendationAggregate:
        rec = self._repository.get_by_id(recommendation_id)
        if rec is None:
            raise RecommendationNotFound(f"Recommendation {recommendation_id} not found")
        return self._to_aggregate(rec)

    def list_recommendations(
        self,
        symbol: str | None = None,
        status: str | None = None,
        direction: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[RecommendationAggregate]:
        filters: dict[str, Any] = {}
        if symbol:
            filters["symbol"] = symbol
        if status:
            filters["status"] = status
        if direction:
            filters["direction"] = direction
        recs = self._repository.list(**filters)
        return [self._to_aggregate(r) for r in recs[offset : offset + limit]]

    def _to_aggregate(self, rec: Recommendation) -> RecommendationAggregate:
        return RecommendationAggregate(
            id=rec.id,
            symbol=rec.symbol,
            direction=rec.direction,
            confidence_score=rec.confidence_score,
            status=rec.status,
            analysis_event_id=rec.analysis_event_id,
            rule_execution_id=rec.rule_execution_id_id if rec.rule_execution_id_id else None,
            strategy_id=rec.strategy_id,
            confidence_evaluation_id=rec.confidence_evaluation_id,
            published_at=rec.published_at,
            created_at=rec.created_at,
        )
