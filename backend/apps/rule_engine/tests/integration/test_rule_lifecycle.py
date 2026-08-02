from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from apps.eventbus.infrastructure.event_bus_factory import get_event_bus, reset_event_bus
from apps.rule_engine.infrastructure.models import RuleExecution

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _use_fake_event_bus() -> None:
    """Integration tests observe published events via the in-memory bus."""
    from django.conf import settings

    settings.EVENT_BUS_IMPLEMENTATION = "fake"
    reset_event_bus()
    yield
    reset_event_bus()


def _build_enriched_data(
    symbol: str = "RELIANCE",
    change_pct: str = "3.50",
    volume: int = 2_000_000,
    avg_volume_20d: int = 500_000,
    current_price: str = "2560.00",
    bb_upper: str | None = "2550.00",
    resistance_levels: list[str] | None = None,
    freshness_validated: bool = True,
    avg_volume_10d: int | None = None,
    technical_extra: dict | None = None,
) -> dict:
    if resistance_levels is None:
        resistance_levels = ["2520.00"]

    price_context = {
        "current_price": current_price,
        "open_price": "2530.00",
        "high": "2570.00",
        "low": "2520.00",
        "prev_close": "2470.00",
        "change_pct": change_pct,
        "volume": volume,
        "avg_volume_20d": avg_volume_20d,
        "avg_volume_10d": avg_volume_10d,
        "circuit_status": "NORMAL",
    }
    technical_context = {
        "rsi_14": "65.5",
        "bb_upper": bb_upper,
        "bb_lower": "2400.00",
        "resistance_levels": [Decimal(v) for v in resistance_levels],
    }
    if technical_extra:
        technical_context.update(technical_extra)

    packet = {
        "symbol": symbol,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "freshness_validated": freshness_validated,
        "price_context": price_context,
        "technical_context": technical_context,
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

    def _setup1_enriched(self) -> dict:
        """A packet satisfying every LongMomentum condition."""
        return _build_enriched_data(
            change_pct="1.00",  # vs prev_close; rule uses change-from-open
            volume=3_000_000,
            avg_volume_20d=5_000_000,  # suppress VolumeSpikeRule
            current_price="103.00",
            bb_upper=None,
            resistance_levels=None,
            avg_volume_10d=900_000,
            technical_extra={
                "vwap": "102.00",
                "ema_20": "101.00",
                "opening_15m_open": "100.00",
                "opening_15m_high": "101.00",
                "opening_15m_low": "100.00",
                "opening_15m_close": "101.00",
            },
        )

    def test_setup1_fires_and_produces_one_execution(self) -> None:
        reset_event_bus()
        get_event_bus()

        from apps.rule_engine.infrastructure.event_handlers import _deserialize_enriched_packet
        from apps.rule_engine.application.rule_evaluation_service import RuleEvaluationService

        enriched = _deserialize_enriched_packet(self._setup1_enriched())

        analysis_event_id = uuid.uuid4()
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            enriched,
            analysis_event_id=analysis_event_id,
        )

        assert len(firings) == 1
        firing = firings[0]
        assert firing.rule_id == "long_momentum_v1"

        execution = RuleExecution.objects.get(
            analysis_event_id=analysis_event_id,
            rule_id="long_momentum_v1",
        )
        assert execution.trigger_data["stop_loss_basis"] in {
            "opening_15m_low",
            "vwap",
        }

    def test_duplicate_delivery_of_same_event_produces_one_execution(self) -> None:
        reset_event_bus()
        get_event_bus()

        from apps.rule_engine.infrastructure.event_handlers import _deserialize_enriched_packet
        from apps.rule_engine.application.rule_evaluation_service import RuleEvaluationService

        enriched = _deserialize_enriched_packet(self._setup1_enriched())

        analysis_event_id = uuid.uuid4()
        service = RuleEvaluationService()

        first = service.evaluate_enriched_packet(
            enriched,
            analysis_event_id=analysis_event_id,
        )
        assert len(first) == 1

        second = service.evaluate_enriched_packet(
            enriched,
            analysis_event_id=analysis_event_id,
        )
        assert len(second) == 0

        assert RuleExecution.objects.filter(
            analysis_event_id=analysis_event_id,
            rule_id="long_momentum_v1",
        ).count() == 1

    def test_setup1_correlation_id_propagates_to_rule_fired_event(self) -> None:
        reset_event_bus()
        bus = get_event_bus()

        from apps.rule_engine.infrastructure.event_handlers import _deserialize_enriched_packet
        from apps.rule_engine.application.rule_evaluation_service import RuleEvaluationService

        enriched = _deserialize_enriched_packet(self._setup1_enriched())

        analysis_event_id = uuid.uuid4()
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            enriched,
            analysis_event_id=analysis_event_id,
        )
        assert len(firings) == 1
        service.publish_rule_firing(firings[0])

        fired_event = next(
            e for e in bus.published_events
            if e.event_type == "rule_engine.RuleFired"
            and e.payload["rule_id"] == "long_momentum_v1"
        )
        assert fired_event.correlation_id == analysis_event_id
        assert fired_event.payload["analysis_event_id"] == str(analysis_event_id)

    def test_stale_packet_never_reaches_setup1(self) -> None:
        reset_event_bus()
        get_event_bus()

        from apps.rule_engine.infrastructure.event_handlers import _deserialize_enriched_packet
        from apps.rule_engine.application.rule_evaluation_service import RuleEvaluationService

        data = self._setup1_enriched()
        data["packet"]["freshness_validated"] = False
        enriched = _deserialize_enriched_packet(data)

        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            enriched,
            analysis_event_id=uuid.uuid4(),
        )

        assert len(firings) == 0
        assert RuleExecution.objects.filter(
            rule_id="long_momentum_v1",
        ).count() == 0

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
