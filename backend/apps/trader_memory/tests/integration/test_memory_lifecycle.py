from __future__ import annotations

import uuid

import pytest

from apps.eventbus.infrastructure.event_bus_factory import get_event_bus, reset_event_bus
from apps.trader_memory.infrastructure.models import MemoryEntry, MemoryProjection

pytestmark = pytest.mark.django_db


class TestMemoryFullLifecycle:
    def _publish_all(self, bus, events):
        for e in events:
            bus.publish(e)

    def test_recommendation_created_stores_memory_entry(self, correlation_id) -> None:
        reset_event_bus()
        bus = get_event_bus()

        from apps.trader_memory.infrastructure.event_handlers import register_handlers
        register_handlers(bus)

        from apps.trader_memory.tests.conftest import make_recommendation_created_event
        rec_id = str(uuid.uuid4())
        event = make_recommendation_created_event(rec_id, correlation_id)
        self._publish_all(bus, [event])

        entries = MemoryEntry.objects.filter(recommendation_id=rec_id)
        assert entries.count() == 1
        assert entries[0].event_type == "recommendations.RecommendationCreated"

    def test_status_change_stores_memory_entry(self, correlation_id) -> None:
        reset_event_bus()
        bus = get_event_bus()

        from apps.trader_memory.infrastructure.event_handlers import register_handlers
        register_handlers(bus)

        from apps.trader_memory.tests.conftest import make_recommendation_status_changed_event
        rec_id = str(uuid.uuid4())
        event = make_recommendation_status_changed_event(rec_id, correlation_id)
        self._publish_all(bus, [event])

        entries = MemoryEntry.objects.filter(recommendation_id=rec_id)
        assert entries.count() == 1
        assert entries[0].event_type == "recommendations.RecommendationStatusChanged"

    def test_full_lifecycle_creates_both_entries(self, correlation_id) -> None:
        reset_event_bus()
        bus = get_event_bus()

        from apps.trader_memory.infrastructure.event_handlers import register_handlers
        register_handlers(bus)

        from apps.trader_memory.tests.conftest import (
            make_recommendation_created_event,
            make_recommendation_status_changed_event,
        )

        rec_id = str(uuid.uuid4())
        events = [
            make_recommendation_created_event(rec_id, correlation_id),
            make_recommendation_status_changed_event(rec_id, correlation_id, "DRAFT", "PUBLISHED"),
        ]
        self._publish_all(bus, events)

        entries = MemoryEntry.objects.filter(recommendation_id=rec_id).order_by("occurred_at")
        assert entries.count() == 2
        assert entries[0].event_type == "recommendations.RecommendationCreated"
        assert entries[1].event_type == "recommendations.RecommendationStatusChanged"

    def test_rebuild_projection_creates_projection(self, strategy_id) -> None:
        from apps.trader_memory.application.memory_query_service import MemoryQueryService

        MemoryEntry.objects.create(
            recommendation_id=str(uuid.uuid4()),
            event_type="recommendations.RecommendationCreated",
            payload={"direction": "BUY", "confidence_score": "0.85"},
            occurred_at=__import__("django").utils.timezone.now(),
        )
        MemoryEntry.objects.create(
            recommendation_id=str(uuid.uuid4()),
            event_type="recommendations.RecommendationStatusChanged",
            payload={"to_status": "ACCEPTED"},
            occurred_at=__import__("django").utils.timezone.now(),
        )

        service = MemoryQueryService()
        projection = service.rebuild_projection(strategy_id)
        assert MemoryProjection.objects.filter(strategy_id=strategy_id).exists()
        assert projection.sample_size >= 0

    def test_idempotent_publish_does_not_duplicate(self, correlation_id) -> None:
        reset_event_bus()
        bus = get_event_bus()

        from apps.trader_memory.infrastructure.event_handlers import register_handlers
        register_handlers(bus)

        from apps.trader_memory.tests.conftest import make_recommendation_created_event
        rec_id = str(uuid.uuid4())
        event = make_recommendation_created_event(rec_id, correlation_id)

        bus.publish(event)
        bus.publish(event)

        entries = MemoryEntry.objects.filter(recommendation_id=rec_id)
        assert entries.count() == 1
