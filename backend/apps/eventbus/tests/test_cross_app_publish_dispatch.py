from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.eventbus.application.services import EventBusService
from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import (
    get_event_bus,
    reset_event_bus,
)


def _reset(implementation: str = "fake") -> None:
    reset_event_bus()
    EventBusService.reset_registration_state()
    from django.conf import settings

    settings.EVENT_BUS_IMPLEMENTATION = implementation


@pytest.mark.django_db
class TestCrossAppPublishDispatch:
    """End-to-end delivery driven by bus.publish(), not direct handler calls.

    These are the only tests in the suite that let the real subscription
    table route an event across application boundaries. If a handler is
    ever double-subscribed, ``publish`` fires it more than once and these
    assertions fail.
    """

    @override_settings(EVENT_BUS_IMPLEMENTATION="fake")
    def test_ta_completed_publish_delivers_packet_built_across_apps(self) -> None:
        _reset()
        bus = get_event_bus()

        from apps.intelligence.infrastructure.event_handlers import (
            register_handlers as register_intelligence,
        )

        register_intelligence(bus)

        packet_built: list[DomainEvent] = []
        bus.subscribe(
            "intelligence.PacketBuilt",
            packet_built.append,
            consumer_group="test_cross_app_ta",
        )

        cid = uuid.uuid4()
        ta_event = DomainEvent.create(
            event_type="technical_analysis.TechnicalAnalysisCompleted",
            payload={
                "symbol": "RELIANCE",
                "snapshot_id": str(uuid.uuid4()),
                "exchange": "NSE",
                "timeframe": "1D",
                "snapshot_timestamp": "2026-07-28T10:00:00+00:00",
                "indicators": {"rsi_14": 62.5, "macd": 1.23},
                "price": {
                    "close": "3124.50",
                    "high": "3145.00",
                    "low": "3100.00",
                    "open": "3110.00",
                    "volume": "1234567",
                },
                "pine_id": "test",
                "pine_version": "5",
            },
            correlation_id=cid,
        )

        with (
            patch("apps.intelligence.infrastructure.ta_completed_handler._save_pine_outputs"),
            patch("apps.intelligence.infrastructure.ta_completed_handler.TASnapshotRepository"),
            patch(
                "apps.intelligence.infrastructure.ta_completed_handler._enrich_with_session_facts",
                side_effect=lambda packet: packet,
            ),
        ):
            bus.publish(ta_event)

        assert len(packet_built) == 1, (
            f"expected exactly one PacketBuilt, got {len(packet_built)} — "
            "handler was likely subscribed multiple times"
        )
        assert packet_built[0].event_type == "intelligence.PacketBuilt"
        assert packet_built[0].payload["symbol"] == "RELIANCE"
        assert packet_built[0].correlation_id == cid
        assert packet_built[0].causation_id == ta_event.event_id

    @override_settings(EVENT_BUS_IMPLEMENTATION="fake")
    def test_rule_fired_publish_yields_exactly_one_recommendation_issued(self) -> None:
        _reset()
        bus = get_event_bus()

        from apps.ai_engine.infrastructure.event_handlers import (
            register_handlers as register_ai_engine,
        )

        register_ai_engine(bus)

        recommendation_issued: list[DomainEvent] = []
        bus.subscribe(
            "ai_engine.RecommendationIssued",
            recommendation_issued.append,
            consumer_group="test_cross_app_ai",
        )

        cid = uuid.uuid4()
        rule_event = DomainEvent.create(
            event_type="rule_engine.RuleFired",
            payload={
                "symbol": "RELIANCE",
                "rule_id": "price_movement_rule",
                "event_type": "price_movement",
                "trigger_data": {"change_pct": "3.5"},
                "analysis_event_id": str(uuid.uuid4()),
            },
            correlation_id=cid,
        )

        orchestrate_calls: list[DomainEvent] = []

        def fake_orchestrate(event: DomainEvent) -> dict[str, object]:
            orchestrate_calls.append(event)
            bus.publish(
                DomainEvent.create(
                    event_type="ai_engine.RecommendationIssued",
                    payload={
                        "symbol": event.payload.get("symbol", ""),
                        "direction": "BUY",
                        "confidence_score": 0.85,
                        "provider": "deepseek",
                    },
                    correlation_id=event.correlation_id,
                    causation_id=event.event_id,
                )
            )
            return {"symbol": event.payload.get("symbol", ""), "direction": "BUY"}

        with patch(
            "apps.ai_engine.infrastructure.ai_reasoning_orchestrator.AIReasoningOrchestrator.orchestrate",
            side_effect=fake_orchestrate,
        ):
            bus.publish(rule_event)

        assert len(orchestrate_calls) == 1, (
            f"expected the ai_engine handler to fire exactly once, got "
            f"{len(orchestrate_calls)} — handler was likely subscribed multiple times"
        )
        assert len(recommendation_issued) == 1, (
            f"expected exactly one RecommendationIssued, got "
            f"{len(recommendation_issued)}"
        )
        assert recommendation_issued[0].event_type == "ai_engine.RecommendationIssued"
        assert recommendation_issued[0].payload["symbol"] == "RELIANCE"
        assert recommendation_issued[0].correlation_id == cid