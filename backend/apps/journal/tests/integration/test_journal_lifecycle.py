from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.journal.infrastructure.models import JournalEntry

pytestmark = pytest.mark.django_db


def _make_event(event_type, cid, account_id, **extra):
    payload = {"account_id": str(account_id)}
    payload.update(extra)
    return DomainEvent.create(
        event_type=event_type,
        payload=payload,
        correlation_id=cid,
    )


class TestJournalFullLifecycle:
    def _publish_all(self, bus, events):
        for e in events:
            bus.publish(e)

    def test_full_lifecycle_forward_order(self, account_id, correlation_id, position_id) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus, get_event_bus
        reset_event_bus()
        bus = get_event_bus()

        from apps.journal.infrastructure.event_handlers import register_handlers
        register_handlers(bus)

        events = [
            _make_event("signals.SignalCreated", correlation_id, account_id, symbol="RELIANCE", signal_type="buy", confidence=0.85),
            _make_event("decisions.TradeDecisionMade", correlation_id, account_id, symbol="RELIANCE", decision="enter_long", quantity=100),
            _make_event("orders.OrderPlaced", correlation_id, account_id, order_id=str(uuid.uuid4()), symbol="RELIANCE", side="buy", quantity=100),
            _make_event("orders.OrderFilled", correlation_id, account_id, order_id=str(uuid.uuid4()), symbol="RELIANCE", side="buy", quantity=100, fill_price=2500.00),
            _make_event("positions.PositionOpened", correlation_id, account_id, position_id=str(position_id), symbol="RELIANCE", quantity=100, entry_price=2500.00),
            _make_event("positions.PositionClosed", correlation_id, account_id, position_id=str(position_id), symbol="RELIANCE", realized_pnl=5000.00),
        ]

        self._publish_all(bus, events)

        entry = JournalEntry.objects.get(correlation_id=correlation_id)
        assert entry.finalized is True
        assert entry.outcome == "won"
        assert entry.realized_pnl == Decimal("5000.00000000")
        assert entry.signal_snapshot is not None
        assert entry.decision_snapshot is not None
        assert len(entry.order_events) == 2
        assert entry.position_id == position_id

    def test_full_lifecycle_reversed_order(self, account_id, position_id) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus, get_event_bus
        reset_event_bus()
        bus = get_event_bus()

        from apps.journal.infrastructure.event_handlers import register_handlers
        register_handlers(bus)

        cid = uuid.uuid4()

        events = [
            _make_event("positions.PositionClosed", cid, account_id, position_id=str(position_id), symbol="RELIANCE", realized_pnl=5000.00),
            _make_event("positions.PositionOpened", cid, account_id, position_id=str(position_id), symbol="RELIANCE", quantity=100, entry_price=2500.00),
            _make_event("orders.OrderFilled", cid, account_id, order_id=str(uuid.uuid4()), symbol="RELIANCE", side="buy", quantity=100, fill_price=2500.00),
            _make_event("orders.OrderPlaced", cid, account_id, order_id=str(uuid.uuid4()), symbol="RELIANCE", side="buy", quantity=100),
            _make_event("decisions.TradeDecisionMade", cid, account_id, symbol="RELIANCE", decision="enter_long", quantity=100),
            _make_event("signals.SignalCreated", cid, account_id, symbol="RELIANCE", signal_type="buy", confidence=0.85),
        ]

        self._publish_all(bus, events)

        entry = JournalEntry.objects.get(correlation_id=cid)
        assert entry.finalized is True
        assert entry.outcome == "won"
        assert entry.realized_pnl == Decimal("5000.00000000")
        assert entry.signal_snapshot is not None
        assert entry.decision_snapshot is not None
        assert len(entry.order_events) == 2
        assert entry.position_id == position_id

    def test_stale_entry_not_finalized_without_position_closed(self, account_id, correlation_id, position_id) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus, get_event_bus
        reset_event_bus()
        bus = get_event_bus()

        from apps.journal.infrastructure.event_handlers import register_handlers
        register_handlers(bus)

        events = [
            _make_event("signals.SignalCreated", correlation_id, account_id, symbol="RELIANCE", signal_type="buy"),
            _make_event("decisions.TradeDecisionMade", correlation_id, account_id, symbol="RELIANCE", decision="enter_long"),
            _make_event("orders.OrderPlaced", correlation_id, account_id, order_id=str(uuid.uuid4()), symbol="RELIANCE"),
            _make_event("orders.OrderFilled", correlation_id, account_id, order_id=str(uuid.uuid4()), symbol="RELIANCE"),
            _make_event("positions.PositionOpened", correlation_id, account_id, position_id=str(position_id), symbol="RELIANCE"),
        ]

        self._publish_all(bus, events)

        entry = JournalEntry.objects.get(correlation_id=correlation_id)
        assert entry.finalized is False

    def test_audit_log_receives_all_events_in_lifecycle(self, account_id, correlation_id, position_id) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus, get_event_bus
        reset_event_bus()
        bus = get_event_bus()

        from apps.journal.infrastructure.event_handlers import register_handlers
        register_handlers(bus)

        from apps.audit_log.infrastructure.event_handlers import register_handlers as register_audit
        register_audit(bus)

        events = [
            _make_event("signals.SignalCreated", correlation_id, account_id, symbol="RELIANCE"),
            _make_event("decisions.TradeDecisionMade", correlation_id, account_id, decision="enter_long"),
            _make_event("orders.OrderPlaced", correlation_id, account_id, order_id=str(uuid.uuid4())),
            _make_event("positions.PositionOpened", correlation_id, account_id, position_id=str(position_id)),
            _make_event("positions.PositionClosed", correlation_id, account_id, position_id=str(position_id), realized_pnl=5000.00),
        ]

        self._publish_all(bus, events)

        from apps.audit_log.infrastructure.models import AuditLogEntry
        assert AuditLogEntry.objects.count() == 5

        event_types_in_audit = set(AuditLogEntry.objects.values_list("action", flat=True))
        for expected in ["signals.SignalCreated", "decisions.TradeDecisionMade", "orders.OrderPlaced", "positions.PositionOpened", "positions.PositionClosed"]:
            assert expected in event_types_in_audit, f"Missing {expected} in audit log"
