from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from apps.eventbus.infrastructure.event_bus_factory import get_event_bus, reset_event_bus
from apps.rule_engine.infrastructure.models import RuleExecution

pytestmark = pytest.mark.django_db


def _build_enriched_data(
    symbol: str = "RELIANCE",
    change_pct: str = "3.50",
    volume: int = 2_000_000,
    avg_volume_20d: int = 500_000,
    current_price: str = "2560.00",
    bb_upper: str | None = "2550.00",
    resistance_levels: list[str] | None = None,
    freshness_validated: bool = True,
) -> dict:
    if resistance_levels is None:
        resistance_levels = ["2520.00"]

    packet = {
        "symbol": symbol,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "freshness_validated": freshness_validated,
        "price_context": {
            "current_price": current_price,
            "open_price": "2530.00",
            "high": "2570.00",
            "low": "2520.00",
            "prev_close": "2470.00",
            "change_pct": change_pct,
            "volume": volume,
            "avg_volume_20d": avg_volume_20d,
            "circuit_status": "NORMAL",
        },
        "technical_context": {
            "rsi_14": "65.5",
            "bb_upper": bb_upper,
            "bb_lower": "2400.00",
            "resistance_levels": [Decimal(v) for v in resistance_levels],
        },
        "breadth_context": {
            "sector_index_change_pct": "0.50",
            "sector_advance_decline": "0.30",
            "nifty_change_pct": "0.40",
            "sensex_change_pct": "0.30",
        },
        "news_context": {},
        "data_quality": {"quality_score": 1.0},
    }
    return {
        "packet": packet,
        "portfolio_context": None,
        "risk_context": None,
    }


class TestRuleLifecycle:
    def test_full_lifecycle_multiple_rules_fire(self) -> None:
        reset_event_bus()
        bus = get_event_bus()

        from apps.rule_engine.infrastructure.event_handlers import register_handlers
        register_handlers(bus)

        from apps.rule_engine.infrastructure.event_handlers import _deserialize_enriched_packet
        from apps.rule_engine.application.rule_evaluation_service import RuleEvaluationService

        enriched_data = _build_enriched_data()
        enriched = _deserialize_enriched_packet(enriched_data)

        analysis_event_id = uuid.uuid4()
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            enriched,
            analysis_event_id=analysis_event_id,
        )

        assert len(firings) == 3
        fired_rules = {f.rule_id for f in firings}
        assert fired_rules == {"price_movement_v1", "volume_spike_v1", "breakout_v1"}

        for firing in firings:
            execution = RuleExecution.objects.get(
                analysis_event_id=analysis_event_id,
                rule_id=firing.rule_id,
            )
            assert execution.symbol == "RELIANCE"
            assert execution.published_event_id is None

            published_id = service.publish_rule_firing(firing)
            assert published_id is not None

            execution.refresh_from_db()
            assert execution.published_event_id == published_id

        published_types = [e.event_type for e in bus.published_events]
        rule_fired_count = published_types.count("rule_engine.RuleFired")
        assert rule_fired_count == 3

    def test_stale_packet_produces_no_firings(self) -> None:
        reset_event_bus()
        get_event_bus()

        from apps.rule_engine.infrastructure.event_handlers import _deserialize_enriched_packet
        from apps.rule_engine.application.rule_evaluation_service import RuleEvaluationService

        enriched_data = _build_enriched_data(freshness_validated=False)
        enriched = _deserialize_enriched_packet(enriched_data)

        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            enriched,
            analysis_event_id=uuid.uuid4(),
        )

        assert len(firings) == 0
        assert RuleExecution.objects.count() == 0

    def test_no_fire_packet_produces_no_firings(self) -> None:
        reset_event_bus()
        get_event_bus()

        from apps.rule_engine.infrastructure.event_handlers import _deserialize_enriched_packet
        from apps.rule_engine.application.rule_evaluation_service import RuleEvaluationService

        enriched_data = _build_enriched_data(
            change_pct="0.50",
            volume=600_000,
            avg_volume_20d=500_000,
            current_price="2450.00",
            bb_upper="2600.00",
            resistance_levels=["2600.00"],
        )
        enriched = _deserialize_enriched_packet(enriched_data)

        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            enriched,
            analysis_event_id=uuid.uuid4(),
        )

        assert len(firings) == 0

    def test_idempotent_evaluation(self) -> None:
        reset_event_bus()
        get_event_bus()

        from apps.rule_engine.infrastructure.event_handlers import _deserialize_enriched_packet
        from apps.rule_engine.application.rule_evaluation_service import RuleEvaluationService

        enriched_data = _build_enriched_data()
        enriched = _deserialize_enriched_packet(enriched_data)

        analysis_event_id = uuid.uuid4()
        service = RuleEvaluationService()

        first_firings = service.evaluate_enriched_packet(
            enriched,
            analysis_event_id=analysis_event_id,
        )

        assert len(first_firings) == 3

        enriched_data_2 = _build_enriched_data()
        enriched_2 = _deserialize_enriched_packet(enriched_data_2)

        second_firings = service.evaluate_enriched_packet(
            enriched_2,
            analysis_event_id=analysis_event_id,
        )

        assert len(second_firings) == 0

        assert RuleExecution.objects.filter(
            analysis_event_id=analysis_event_id,
        ).count() == 3

    def test_publish_through_event_bus(
        self, analysis_event_id
    ) -> None:
        reset_event_bus()
        bus = get_event_bus()

        from apps.rule_engine.infrastructure.event_handlers import _deserialize_enriched_packet
        from apps.rule_engine.application.rule_evaluation_service import RuleEvaluationService

        enriched_data = _build_enriched_data()
        enriched = _deserialize_enriched_packet(enriched_data)

        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            enriched,
            analysis_event_id=analysis_event_id,
        )

        assert len(firings) >= 1

        for firing in firings:
            service.publish_rule_firing(firing)

        rule_fired_events = [
            e for e in bus.published_events
            if e.event_type == "rule_engine.RuleFired"
        ]

        assert len(rule_fired_events) == len(firings)

        for event in rule_fired_events:
            assert event.payload["analysis_event_id"] == str(analysis_event_id)
            assert event.payload["symbol"] == "RELIANCE"
            assert event.payload["rule_id"] in {"price_movement_v1", "volume_spike_v1", "breakout_v1"}
            assert event.correlation_id == analysis_event_id
