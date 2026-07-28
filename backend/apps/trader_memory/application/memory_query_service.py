from __future__ import annotations

import uuid
from decimal import Decimal

from core.services import BaseService
from apps.trader_memory.domain.entities import MemoryEntrySnapshot, MemoryProjectionSnapshot
from apps.trader_memory.domain.exceptions import MemoryEntryNotFound
from apps.trader_memory.infrastructure.models import MemoryEntry, MemoryProjection
from apps.trader_memory.infrastructure.repositories import MemoryEntryRepository, MemoryProjectionRepository


class MemoryQueryService(BaseService):
    def __init__(self) -> None:
        super().__init__()
        self._entry_repo = MemoryEntryRepository()
        self._projection_repo = MemoryProjectionRepository()

    def list_entries(
        self,
        recommendation_id: str | None = None,
        event_type: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[MemoryEntrySnapshot]:
        filters: dict = {}
        if recommendation_id:
            filters["recommendation_id"] = recommendation_id
        if event_type:
            filters["event_type"] = event_type
        entries = self._entry_repo.list(**filters)
        return [
            MemoryEntrySnapshot(
                recommendation_id=uuid.UUID(e.recommendation_id),
                event_type=e.event_type,
                payload=dict(e.payload) if e.payload else {},
                occurred_at=e.occurred_at,
            )
            for e in entries[offset : offset + limit]
        ]

    def get_projection(self, strategy_id: uuid.UUID) -> MemoryProjectionSnapshot:
        projection = self._projection_repo.get_by_strategy_id(strategy_id)
        if projection is None:
            raise MemoryEntryNotFound(
                f"Projection not found for strategy_id={strategy_id}"
            )
        return MemoryProjectionSnapshot(
            strategy_id=uuid.UUID(projection.strategy_id),
            sample_size=projection.sample_size,
            win_rate=projection.win_rate,
            avg_confidence_at_publish=projection.avg_confidence_at_publish,
            last_recomputed_at=projection.last_recomputed_at,
        )

    def rebuild_projection(self, strategy_id: str) -> MemoryProjection:
        from django.db.models import Count
        from django.utils import timezone

        entries = MemoryEntry.objects.filter(
            event_type="recommendations.RecommendationCreated",
            recommendation_id__isnull=False,
        )

        sample_size = entries.aggregate(
            sample_size=Count("id", distinct=True),
        ).get("sample_size", 0) or 0

        accepted = MemoryEntry.objects.filter(
            event_type="recommendations.RecommendationStatusChanged",
            payload__to_status="ACCEPTED",
            recommendation_id__in=entries.values("recommendation_id"),
        ).count()

        total_status = MemoryEntry.objects.filter(
            event_type="recommendations.RecommendationStatusChanged",
            payload__to_status__in=["ACCEPTED", "REJECTED"],
            recommendation_id__in=entries.values("recommendation_id"),
        ).count()

        win_rate = Decimal(str(accepted / total_status)) if total_status > 0 else Decimal("0")
        avg_conf = Decimal("0.70")

        projection, _ = MemoryProjection.objects.update_or_create(
            strategy_id=strategy_id,
            defaults={
                "sample_size": sample_size,
                "win_rate": win_rate,
                "avg_confidence_at_publish": avg_conf,
                "last_recomputed_at": timezone.now(),
            },
        )
        return projection
