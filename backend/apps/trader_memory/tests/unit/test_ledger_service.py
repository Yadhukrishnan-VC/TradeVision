from __future__ import annotations

from datetime import datetime, timezone

import pytest

from apps.trader_memory.application.ledger_service import LedgerService
from apps.trader_memory.domain.exceptions import DuplicateMemoryEntry
from apps.trader_memory.infrastructure.models import MemoryEntry

pytestmark = pytest.mark.django_db


class TestLedgerService:
    def test_append_entry_creates_memory_entry(self, recommendation_id: str) -> None:
        service = LedgerService()
        entry = service.append_entry(
            recommendation_id=recommendation_id,
            event_type="test.Event",
            payload={"key": "value"},
        )
        assert MemoryEntry.objects.filter(id=entry.id).exists()
        assert entry.recommendation_id == recommendation_id
        assert entry.event_type == "test.Event"
        assert entry.payload == {"key": "value"}

    def test_append_entry_duplicate_raises_error(self, recommendation_id: str) -> None:
        service = LedgerService()
        now = datetime.now(timezone.utc)
        service.append_entry(
            recommendation_id=recommendation_id,
            event_type="test.Event",
            payload={},
            occurred_at=now,
        )
        with pytest.raises(DuplicateMemoryEntry):
            service.append_entry(
                recommendation_id=recommendation_id,
                event_type="test.Event",
                payload={},
                occurred_at=now,
            )

    def test_handle_recommendation_created(self, created_event) -> None:
        service = LedgerService()
        service.handle_recommendation_created(created_event)
        rec_id = created_event.payload["recommendation_id"]
        entries = MemoryEntry.objects.filter(recommendation_id=rec_id)
        assert entries.count() == 1
        assert entries[0].event_type == "recommendations.RecommendationCreated"
        assert entries[0].payload["direction"] == "BUY"

    def test_handle_recommendation_status_changed(self, status_changed_event) -> None:
        service = LedgerService()
        service.handle_recommendation_status_changed(status_changed_event)
        rec_id = status_changed_event.payload["recommendation_id"]
        entries = MemoryEntry.objects.filter(recommendation_id=rec_id)
        assert entries.count() == 1
        assert entries[0].event_type == "recommendations.RecommendationStatusChanged"
        assert entries[0].payload["to_status"] == "PUBLISHED"

    def test_idempotent_handling(self, created_event) -> None:
        service = LedgerService()
        service.handle_recommendation_created(created_event)
        from django.db import IntegrityError
        with pytest.raises(DuplicateMemoryEntry):
            service.handle_recommendation_created(created_event)
        rec_id = created_event.payload["recommendation_id"]
        assert MemoryEntry.objects.filter(recommendation_id=rec_id).count() == 1
