from __future__ import annotations

import uuid
from typing import Any

from core.repository import BaseRepository
from apps.recommendations.infrastructure.models import Recommendation


class RecommendationRepository(BaseRepository[Recommendation]):
    def get_by_id(self, entity_id: uuid.UUID) -> Recommendation | None:
        try:
            return Recommendation.objects.get(id=entity_id)
        except Recommendation.DoesNotExist:
            return None

    def list(self, **filters: Any) -> list[Recommendation]:
        return list(Recommendation.objects.filter(**filters))

    def create(self, entity: Recommendation) -> Recommendation:
        entity.full_clean()
        entity.save()
        return entity

    def update(self, entity: Recommendation) -> Recommendation:
        entity.full_clean()
        entity.save()
        return entity

    def delete(self, entity_id: uuid.UUID) -> None:
        Recommendation.objects.filter(id=entity_id).delete()

    def exists(self, entity_id: uuid.UUID) -> bool:
        return Recommendation.objects.filter(id=entity_id).exists()

    def count(self, **filters: Any) -> int:
        return Recommendation.objects.filter(**filters).count()
