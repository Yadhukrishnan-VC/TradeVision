from __future__ import annotations

from typing import Any

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.intelligence.models import PineOutput
from apps.intelligence.services import MarketContextService
from apps.signals_engine.infrastructure.event_handlers import register_handlers
from apps.signals_engine.infrastructure.models import Signal


class TestSignalLifecycleIntegration:
    @pytest.fixture(autouse=True)
    def _setup(self, db: Any) -> None:
        register_handlers(get_event_bus())

    def test_full_path_from_raw_alert_to_context(
        self, raw_alert_event: DomainEvent, db: Any
    ) -> None:
        from apps.signals_engine.infrastructure.tasks import handle_raw_alert_received

        handle_raw_alert_received(raw_alert_event)

        signal_count = Signal.objects.count()
        assert signal_count == 1

        pine_count = PineOutput.objects.filter(
            symbol="RELIANCE",
            indicator_name="pine_composite",
        ).count()
        assert pine_count == 1

        bus = get_event_bus()
        signal_created = [
            e
            for e in bus.published_events
            if e.event_type == "signals.SignalCreated"
        ]
        assert len(signal_created) == 1
        assert signal_created[0].payload["symbol"] == "RELIANCE"

    def test_pine_output_values_written_correctly(
        self, raw_alert_event: DomainEvent, db: Any
    ) -> None:
        from apps.signals_engine.infrastructure.tasks import handle_raw_alert_received

        handle_raw_alert_received(raw_alert_event)

        pine = PineOutput.objects.get(
            symbol="RELIANCE",
            timeframe="1h",
            indicator_name="pine_composite",
        )
        assert pine.values.get("rsi_14") == 62.5
        assert pine.values.get("macd") == 12.30
        assert pine.source == "tradingview"

    def test_get_pine_outputs_returns_non_empty_after_write(
        self, raw_alert_event: DomainEvent, db: Any
    ) -> None:
        from apps.signals_engine.infrastructure.tasks import handle_raw_alert_received

        handle_raw_alert_received(raw_alert_event)

        service = MarketContextService()
        pine_outputs = service._get_pine_outputs("RELIANCE", ["1h"])

        assert "1h" in pine_outputs
        assert pine_outputs["1h"] != {}
        assert pine_outputs["1h"].get("rsi_14") == 62.5

    def test_duplicate_alert_creates_no_extra_signal(
        self, raw_alert_event: DomainEvent, db: Any
    ) -> None:
        from apps.signals_engine.infrastructure.tasks import handle_raw_alert_received

        handle_raw_alert_received(raw_alert_event)
        handle_raw_alert_received(raw_alert_event)

        assert Signal.objects.count() == 1

        bus = get_event_bus()
        signal_created = [
            e
            for e in bus.published_events
            if e.event_type == "signals.SignalCreated"
        ]
        assert len(signal_created) == 1

    def test_existing_intelligence_test_suite_still_passes(
        self, db: Any
    ) -> None:
        from apps.intelligence.tests.test_event_consumers import TestIntelligencePacketRoundTrip

        tester = TestIntelligencePacketRoundTrip()
        tester.test_every_field_survives_deserialisation()
        tester.test_required_fields_when_optional_blocks_are_none()
        tester.test_enriched_packet_round_trip_with_all_blocks()
