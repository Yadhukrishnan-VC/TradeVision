from __future__ import annotations

import uuid

import pytest

from apps.audit_log.infrastructure.models import AuditLogEntry
from apps.eventbus.domain.events import DomainEvent

pytestmark = pytest.mark.django_db


class TestAuditBroadSubscription:
    def test_audit_log_receives_all_events_via_wildcard(self) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus, get_event_bus
        reset_event_bus()
        bus = get_event_bus()

        from apps.audit_log.infrastructure.event_handlers import register_handlers
        register_handlers(bus)

        event_types = [
            "signals.SignalCreated",
            "decisions.TradeDecisionMade",
            "orders.OrderPlaced",
            "orders.OrderFilled",
            "positions.PositionOpened",
            "positions.PositionClosed",
            "risk.AlertRaised",
            "accounts.UserLoggedIn",
            "system.HandlerDeadLettered",
        ]

        cid = uuid.uuid4()
        for et in event_types:
            event = DomainEvent.create(
                event_type=et,
                payload={"test": True, "account_id": str(uuid.uuid4())},
                correlation_id=cid,
            )
            bus.publish(event)

        assert AuditLogEntry.objects.count() == len(event_types)

        logged_actions = set(AuditLogEntry.objects.values_list("action", flat=True))
        for et in event_types:
            assert et in logged_actions, f"Missing {et} in audit log"

    def test_audit_log_persists_full_payload(self) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus, get_event_bus
        reset_event_bus()
        bus = get_event_bus()

        from apps.audit_log.infrastructure.event_handlers import register_handlers
        register_handlers(bus)

        payload = {"symbol": "RELIANCE", "quantity": 100, "price": 2500.50, "account_id": str(uuid.uuid4())}
        event = DomainEvent.create(
            event_type="orders.OrderPlaced",
            payload=payload,
            correlation_id=uuid.uuid4(),
        )
        bus.publish(event)

        entry = AuditLogEntry.objects.get(action="orders.OrderPlaced")
        assert entry.metadata == payload
        assert entry.metadata["symbol"] == "RELIANCE"
        assert entry.metadata["price"] == 2500.50
