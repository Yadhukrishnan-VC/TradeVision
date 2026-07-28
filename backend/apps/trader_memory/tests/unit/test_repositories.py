from __future__ import annotations

import uuid

import pytest

from apps.trader_memory.infrastructure.models import MemoryEntry, MemoryProjection
from apps.trader_memory.infrastructure.repositories import MemoryEntryRepository, MemoryProjectionRepository

pytestmark = pytest.mark.django_db


class TestMemoryEntryRepository:
    def test_create_and_get(self) -> None:
        repo = MemoryEntryRepository()
        entry = MemoryEntry(
            recommendation_id=str(uuid.uuid4()),
            event_type="test.Event",
            payload={"key": "value"},
            occurred_at=__import__("django").utils.timezone.now(),
        )
        created = repo.create(entry)
        fetched = repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.recommendation_id == entry.recommendation_id

    def test_list_with_filters(self) -> None:
        repo = MemoryEntryRepository()
        rec_id = str(uuid.uuid4())
        for i in range(3):
            MemoryEntry.objects.create(
                recommendation_id=rec_id,
                event_type=f"test.Event.{i}",
                payload={},
                occurred_at=__import__("django").utils.timezone.now(),
            )
        entries = repo.list(recommendation_id=rec_id)
        assert len(entries) == 3

    def test_count(self) -> None:
        repo = MemoryEntryRepository()
        rec_id = str(uuid.uuid4())
        MemoryEntry.objects.create(
            recommendation_id=rec_id,
            event_type="test.Event",
            payload={},
            occurred_at=__import__("django").utils.timezone.now(),
        )
        assert repo.count() == 1

    def test_delete(self) -> None:
        repo = MemoryEntryRepository()
        entry = MemoryEntry.objects.create(
            recommendation_id=str(uuid.uuid4()),
            event_type="test.Event",
            payload={},
            occurred_at=__import__("django").utils.timezone.now(),
        )
        repo.delete(entry.id)
        assert repo.get_by_id(entry.id) is None


class TestMemoryProjectionRepository:
    def test_create_and_get_by_strategy(self) -> None:
        repo = MemoryProjectionRepository()
        projection = MemoryProjection.objects.create(
            strategy_id=str(uuid.uuid4()),
            sample_size=10,
            win_rate=0.5,
        )
        fetched = repo.get_by_strategy_id(projection.strategy_id)
        assert fetched is not None
        assert fetched.sample_size == 10

    def test_update(self) -> None:
        repo = MemoryProjectionRepository()
        projection = MemoryProjection.objects.create(
            strategy_id=str(uuid.uuid4()),
            sample_size=10,
            win_rate=0.5,
        )
        projection.sample_size = 20
        repo.update(projection)
        fetched = repo.get_by_id(projection.id)
        assert fetched.sample_size == 20

    def test_exists(self) -> None:
        repo = MemoryProjectionRepository()
        projection = MemoryProjection.objects.create(
            strategy_id=str(uuid.uuid4()),
        )
        assert repo.exists(projection.id) is True
        assert repo.exists(uuid.uuid4()) is False
