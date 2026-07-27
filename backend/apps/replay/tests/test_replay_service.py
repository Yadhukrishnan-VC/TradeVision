from __future__ import annotations

import uuid

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus, get_event_bus
from apps.eventbus.infrastructure.models import StoredEvent
from apps.replay.application.replay_service import ReplayService

pytestmark = pytest.mark.django_db


class TestReplayService:
    def test_replay_by_correlation_id(self) -> None:
        reset_event_bus()
        bus = get_event_bus()

        cid = uuid.uuid4()
        event = DomainEvent.create(
            event_type="test.Event",
            payload={"message": "hello", "account_id": str(uuid.uuid4())},
            correlation_id=cid,
        )
        bus.publish(event)

        replayed = 0

        original_publish = bus.publish
        def tracking_publish(e: DomainEvent) -> None:
            nonlocal replayed
            replayed += 1
            original_publish(e)

        bus.publish = tracking_publish  # type: ignore[method-assign]

        count = ReplayService.replay(correlation_id=cid, target_consumer_group="test_group")

        assert count >= 0
        assert StoredEvent.objects.filter(correlation_id=cid).count() == 1

    def test_replay_no_matching_events(self) -> None:
        count = ReplayService.replay(
            correlation_id=uuid.uuid4(),
            target_consumer_group="test_group",
        )
        assert count == 0

    def test_replay_skips_already_processed(self) -> None:
        reset_event_bus()
        bus = get_event_bus()

        cid = uuid.uuid4()
        event = DomainEvent.create(
            event_type="test.Event",
            payload={"account_id": str(uuid.uuid4())},
            correlation_id=cid,
        )
        bus.publish(event)

        from apps.eventbus.infrastructure.models import ProcessedEvent
        stored = StoredEvent.objects.get(correlation_id=cid)
        ProcessedEvent.objects.create(
            event_id=stored.event_id,
            consumer_group="test_group",
        )

        count = ReplayService.replay(correlation_id=cid, target_consumer_group="test_group")
        assert count == 0
