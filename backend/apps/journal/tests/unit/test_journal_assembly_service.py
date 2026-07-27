from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.journal.application.journal_assembly_service import JournalAssemblyService
from apps.journal.infrastructure.models import JournalEntry, JournalEventLog

pytestmark = pytest.mark.django_db


class TestJournalAssemblyService:
    def test_signal_creates_entry(self, signal_created_event) -> None:
        service = JournalAssemblyService()
        service.handle(signal_created_event)

        entry = JournalEntry.objects.get(correlation_id=signal_created_event.correlation_id)
        assert entry.signal_snapshot is not None
        assert entry.signal_snapshot["symbol"] == "RELIANCE"
        assert entry.finalized is False

    def test_decision_updates_entry(self, signal_created_event, decision_made_event) -> None:
        service = JournalAssemblyService()
        service.handle(signal_created_event)
        service.handle(decision_made_event)

        entry = JournalEntry.objects.get(correlation_id=signal_created_event.correlation_id)
        assert entry.signal_snapshot is not None
        assert entry.decision_snapshot is not None
        assert entry.decision_snapshot["decision"] == "enter_long"

    def test_order_events_append(self, signal_created_event, order_placed_event, order_filled_event) -> None:
        service = JournalAssemblyService()
        service.handle(signal_created_event)
        service.handle(order_placed_event)
        service.handle(order_filled_event)

        entry = JournalEntry.objects.get(correlation_id=signal_created_event.correlation_id)
        assert len(entry.order_events) == 2
        assert entry.order_events[0]["event_type"] == "orders.OrderPlaced"
        assert entry.order_events[1]["event_type"] == "orders.OrderFilled"

    def test_position_opened_updates_position_id(
        self, signal_created_event, position_opened_event, position_id
    ) -> None:
        service = JournalAssemblyService()
        service.handle(signal_created_event)
        service.handle(position_opened_event)

        entry = JournalEntry.objects.get(correlation_id=signal_created_event.correlation_id)
        assert entry.position_id == position_id

    def test_position_closed_finalizes_entry(
        self, signal_created_event, position_opened_event, position_closed_event
    ) -> None:
        service = JournalAssemblyService()
        service.handle(signal_created_event)
        service.handle(position_opened_event)
        service.handle(position_closed_event)

        entry = JournalEntry.objects.get(correlation_id=signal_created_event.correlation_id)
        assert entry.finalized is True
        assert entry.outcome == "won"
        assert entry.realized_pnl == Decimal("5000.00000000")
        assert entry.finalized_at is not None

    def test_position_closed_losing_sets_outcome_lost(
        self, signal_created_event, position_opened_event, position_closed_losing_event
    ) -> None:
        service = JournalAssemblyService()
        service.handle(signal_created_event)
        service.handle(position_opened_event)
        service.handle(position_closed_losing_event)

        entry = JournalEntry.objects.get(correlation_id=signal_created_event.correlation_id)
        assert entry.finalized is True
        assert entry.outcome == "lost"
        assert entry.realized_pnl == Decimal("-2500.00000000")

    def test_position_closed_breakeven_sets_outcome(
        self, correlation_id, account_id, position_id
    ) -> None:
        from apps.journal.tests.conftest import make_event

        service = JournalAssemblyService()
        service.handle(make_event("signals.SignalCreated", correlation_id, account_id, {"symbol": "TEST"}))
        service.handle(make_event("positions.PositionOpened", correlation_id, account_id, {"position_id": str(position_id)}))
        service.handle(make_event("positions.PositionClosed", correlation_id, account_id, {"position_id": str(position_id), "realized_pnl": 0}))

        entry = JournalEntry.objects.get(correlation_id=correlation_id)
        assert entry.finalized is True
        assert entry.outcome == "breakeven"
        assert entry.realized_pnl == Decimal("0.00000000")

    def test_order_independence(self, account_id, position_id) -> None:
        from apps.journal.tests.conftest import make_event
        from dataclasses import replace

        base_cid = uuid.uuid4()
        signal = make_event("signals.SignalCreated", base_cid, account_id, {"symbol": "ABC"})
        decision = make_event("decisions.TradeDecisionMade", base_cid, account_id, {"decision": "enter_long", "quantity": 50})
        order = make_event("orders.OrderPlaced", base_cid, account_id, {"order_id": str(uuid.uuid4()), "symbol": "ABC", "quantity": 50})
        position_open = make_event("positions.PositionOpened", base_cid, account_id, {"position_id": str(position_id), "symbol": "ABC", "quantity": 50, "entry_price": 100.0})
        position_close = make_event("positions.PositionClosed", base_cid, account_id, {"position_id": str(position_id), "realized_pnl": 1000.0})

        events = [signal, decision, order, position_open, position_close]

        import itertools
        permutations = list(itertools.permutations(events))
        tested_permutations = [permutations[0], permutations[len(permutations)//2], permutations[-1]]

        for perm_idx, perm in enumerate(tested_permutations):
            cid = uuid.uuid4()
            perm = [
                replace(e, event_id=uuid.uuid4(), correlation_id=cid)
                for e in perm
            ]

            for e in perm:
                if "position_id" not in e.payload and "positions.PositionClosed" in e.event_type:
                    e.payload["position_id"] = str(position_id)

            from apps.journal.infrastructure.models import JournalEventLog
            JournalEventLog.objects.filter(consumer="journal").delete()
            JournalEntry.objects.all().delete()

            service = JournalAssemblyService()
            for e in perm:
                service.handle(e)

            entry = JournalEntry.objects.get(correlation_id=cid)
            assert entry.finalized is True, f"Permutation {perm_idx}: entry not finalized"
            assert entry.outcome == "won", f"Permutation {perm_idx}: expected won, got {entry.outcome}"
            assert entry.realized_pnl == Decimal("1000.00000000"), f"Permutation {perm_idx}: pnl mismatch"
            assert entry.signal_snapshot is not None, f"Permutation {perm_idx}: signal_snapshot is None"
            assert entry.decision_snapshot is not None, f"Permutation {perm_idx}: decision_snapshot is None"
            assert entry.position_id == position_id, f"Permutation {perm_idx}: position_id mismatch"

    def test_idempotency_via_event_log(self, signal_created_event) -> None:
        service = JournalAssemblyService()
        service.handle(signal_created_event)
        service.handle(signal_created_event)

        entries = JournalEntry.objects.filter(correlation_id=signal_created_event.correlation_id)
        assert entries.count() == 1

    def test_entry_finalized_event_published(self, signal_created_event, position_opened_event, position_closed_event) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus, get_event_bus
        reset_event_bus()
        bus = get_event_bus()

        from apps.journal.infrastructure.event_handlers import register_handlers
        register_handlers(bus)

        service = JournalAssemblyService()
        service.handle(signal_created_event)
        service.handle(position_opened_event)
        service.handle(position_closed_event)

        published_types = [e.event_type for e in bus.published_events]
        assert "journal.EntryFinalized" in published_types
        finalized_event = next(e for e in bus.published_events if e.event_type == "journal.EntryFinalized")
        assert finalized_event.payload["correlation_id"] == str(signal_created_event.correlation_id)
        assert finalized_event.payload["outcome"] == "won"

    def test_risk_event_no_op(self, correlation_id, account_id) -> None:
        from apps.journal.tests.conftest import make_event
        event = make_event("risk.AlertRaised", correlation_id, account_id, {"alert_type": "margin_warning"})
        service = JournalAssemblyService()
        service.handle(event)

        assert JournalEntry.objects.filter(correlation_id=correlation_id).count() == 1


class TestJournalEntryManager:
    def test_journal_event_log_tracks_applied(self, signal_created_event) -> None:
        service = JournalAssemblyService()
        service.handle(signal_created_event)

        assert JournalEventLog.objects.has_been_applied(
            signal_created_event.event_id, "journal"
        ) is True
