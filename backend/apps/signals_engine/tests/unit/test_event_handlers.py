from __future__ import annotations

from typing import Any

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.intelligence.models import PineOutput
from apps.signals_engine.infrastructure.event_handlers import register_handlers
from apps.signals_engine.infrastructure.models import Signal


class TestSignalEventHandlers:
    def test_register_handlers_adds_subscription(self) -> None:
        bus = get_event_bus()
        register_handlers(bus)
        assert "ingestion.RawAlertReceived" in bus._handlers

    def test_handler_creates_signal_and_pine_output(
        self, raw_alert_event: DomainEvent, db: Any
    ) -> None:
        from apps.signals_engine.infrastructure.tasks import handle_raw_alert_received

        handle_raw_alert_received(raw_alert_event)

        assert Signal.objects.count() == 1
        signal = Signal.objects.first()
        assert signal is not None
        assert signal.instrument_symbol == "RELIANCE"
        assert signal.direction == "BUY"

        pine = PineOutput.objects.filter(
            symbol="RELIANCE",
            timeframe="1h",
            indicator_name="pine_composite",
        ).first()
        assert pine is not None
        assert pine.values.get("rsi_14") == 62.5

    def test_handler_publishes_signal_created_event(
        self, raw_alert_event: DomainEvent, db: Any
    ) -> None:
        from apps.signals_engine.infrastructure.tasks import handle_raw_alert_received

        bus = get_event_bus()
        handle_raw_alert_received(raw_alert_event)

        published = bus.published_events
        signal_created = [e for e in published if e.event_type == "signals.SignalCreated"]
        assert len(signal_created) == 1
        payload = signal_created[0].payload
        assert payload["symbol"] == "RELIANCE"
        assert payload["direction"] == "BUY"
        assert payload["signal_id"] is not None

    def test_handler_skips_duplicate_alert(
        self, raw_alert_event: DomainEvent, db: Any
    ) -> None:
        from apps.signals_engine.infrastructure.tasks import handle_raw_alert_received

        handle_raw_alert_received(raw_alert_event)
        handle_raw_alert_received(raw_alert_event)

        assert Signal.objects.count() == 1

        bus = get_event_bus()
        dup_ignored = [
            e
            for e in bus.published_events
            if e.event_type == "signals.SignalDuplicateIgnored"
        ]
        assert len(dup_ignored) == 1

    def test_handler_publishes_signal_duplicate_ignored(
        self, raw_alert_event: DomainEvent, db: Any
    ) -> None:
        from apps.signals_engine.infrastructure.tasks import handle_raw_alert_received

        handle_raw_alert_received(raw_alert_event)
        handle_raw_alert_received(raw_alert_event)

        bus = get_event_bus()
        dup_events = [
            e
            for e in bus.published_events
            if e.event_type == "signals.SignalDuplicateIgnored"
        ]
        assert len(dup_events) == 1
        assert dup_events[0].payload["reason"] == "duplicate_within_window"
