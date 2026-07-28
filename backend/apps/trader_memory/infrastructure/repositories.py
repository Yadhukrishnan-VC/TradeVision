from __future__ import annotations

import uuid
from typing import Any

from core.repository import BaseRepository
from apps.trader_memory.infrastructure.models import MemoryEntry, MemoryProjection


class MemoryEntryRepository(BaseRepository[MemoryEntry]):
    def get_by_id(self, entity_id: uuid.UUID) -> MemoryEntry | None:
        try:
            return MemoryEntry.objects.get(id=entity_id)
        except MemoryEntry.DoesNotExist:
            return None

    def list(self, **filters: Any) -> list[MemoryEntry]:
        return list(MemoryEntry.objects.filter(**filters))

    def create(self, entity: MemoryEntry) -> MemoryEntry:
        entity.full_clean()
        entity.save()
        return entity

    def update(self, entity: MemoryEntry) -> MemoryEntry:
        entity.full_clean()
        entity.save()
        return entity

    def delete(self, entity_id: uuid.UUID) -> None:
        MemoryEntry.objects.filter(id=entity_id).delete()

    def exists(self, entity_id: uuid.UUID) -> bool:
        return MemoryEntry.objects.filter(id=entity_id).exists()

    def count(self, **filters: Any) -> int:
        return MemoryEntry.objects.filter(**filters).count()


class MemoryProjectionRepository(BaseRepository[MemoryProjection]):
    def get_by_id(self, entity_id: uuid.UUID) -> MemoryProjection | None:
        try:
            return MemoryProjection.objects.get(id=entity_id)
        except MemoryProjection.DoesNotExist:
            return None

    def get_by_strategy_id(self, strategy_id: str) -> MemoryProjection | None:
        try:
            return MemoryProjection.objects.get(strategy_id=strategy_id)
        except MemoryProjection.DoesNotExist:
            return None

    def list(self, **filters: Any) -> list[MemoryProjection]:
        return list(MemoryProjection.objects.filter(**filters))

    def create(self, entity: MemoryProjection) -> MemoryProjection:
        entity.full_clean()
        entity.save()
        return entity

    def update(self, entity: MemoryProjection) -> MemoryProjection:
        entity.full_clean()
        entity.save()
        return entity

    def delete(self, entity_id: uuid.UUID) -> None:
        MemoryProjection.objects.filter(id=entity_id).delete()

    def exists(self, entity_id: uuid.UUID) -> bool:
        return MemoryProjection.objects.filter(id=entity_id).exists()

    def count(self, **filters: Any) -> int:
        return MemoryProjection.objects.filter(**filters).count()
