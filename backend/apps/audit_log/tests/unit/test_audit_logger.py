from __future__ import annotations

import uuid

import pytest

from apps.audit_log.infrastructure.models import AuditLogEntry
from apps.audit_log.services import AuditLogger
from apps.eventbus.domain.events import DomainEvent

pytestmark = pytest.mark.django_db


class TestAuditLogger:
    def test_log_event_creates_entry(self) -> None:
        event = DomainEvent.create(
            event_type="signals.SignalCreated",
            payload={"symbol": "RELIANCE", "signal_type": "buy"},
            correlation_id=uuid.uuid4(),
        )
        logger = AuditLogger()
        logger.log_event(event)

        entry = AuditLogEntry.objects.get(action="signals.SignalCreated")
        assert entry.actor == "system"
        assert entry.target_type == "signals"
        assert entry.target_id == str(event.correlation_id)
        assert entry.metadata == event.payload
        assert entry.occurred_at == event.occurred_at

    def test_log_multiple_events(self) -> None:
        logger = AuditLogger()
        events = [
            DomainEvent.create("orders.OrderPlaced", {"order_id": "1"}, correlation_id=uuid.uuid4()),
            DomainEvent.create("orders.OrderFilled", {"order_id": "1"}, correlation_id=uuid.uuid4()),
            DomainEvent.create("positions.PositionOpened", {"position_id": "1"}, correlation_id=uuid.uuid4()),
        ]
        for e in events:
            logger.log_event(e)

        assert AuditLogEntry.objects.count() == 3

    def test_actor_determination_user(self) -> None:
        event = DomainEvent.create(
            event_type="accounts.UserLoggedIn",
            payload={"user_id": str(uuid.uuid4())},
            correlation_id=uuid.uuid4(),
        )
        logger = AuditLogger()
        logger.log_event(event)

        entry = AuditLogEntry.objects.get(action="accounts.UserLoggedIn")
        assert entry.actor == "user"

    def test_actor_determination_ai(self) -> None:
        event = DomainEvent.create(
            event_type="recommendations.RecommendationGenerated",
            payload={"recommendation_id": str(uuid.uuid4())},
            correlation_id=uuid.uuid4(),
        )
        logger = AuditLogger()
        logger.log_event(event)

        entry = AuditLogEntry.objects.get(action="recommendations.RecommendationGenerated")
        assert entry.actor == "ai"

    def test_actor_determination_system(self) -> None:
        event = DomainEvent.create(
            event_type="system.HandlerDeadLettered",
            payload={"original_event_id": str(uuid.uuid4())},
            correlation_id=uuid.uuid4(),
        )
        logger = AuditLogger()
        logger.log_event(event)

        entry = AuditLogEntry.objects.get(action="system.HandlerDeadLettered")
        assert entry.actor == "system"


class TestAuditLogEntryAppendOnly:
    def test_update_raises(self) -> None:
        with pytest.raises(NotImplementedError):
            AuditLogEntry.objects.update(action="modified")

    def test_delete_raises(self) -> None:
        with pytest.raises(NotImplementedError):
            AuditLogEntry.objects.delete()

    def test_bulk_delete_via_queryset_raises(self) -> None:
        event = DomainEvent.create(
            event_type="test.event",
            payload={},
            correlation_id=uuid.uuid4(),
        )
        AuditLogger().log_event(event)

        qs = AuditLogEntry.objects.all()
        with pytest.raises(NotImplementedError):
            qs.delete()
