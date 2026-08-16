from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import replace

import pytest

from apps.eventbus.infrastructure.event_bus_factory import get_event_bus, reset_event_bus
from apps.rule_engine.application.rule_evaluation_service import RuleEvaluationService
from apps.rule_engine.domain.exceptions import RuleEvaluationError
from apps.rule_engine.infrastructure.models import RuleExecution

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_go_gate(gate_configs: Callable[..., None]) -> None:
    """Every firing test here clears ADR-029's go/no-go gate.

    These tests exercise live (non-replay) evaluation mechanics, so each fired
    rule needs an enabled RuleConfig with a GO verdict for the packet's regime.
    """
    gate_configs()


def _with_regime(packet, regime: str):
    return replace(packet, regime=regime)


class TestRuleEvaluationService:
    def test_evaluate_price_movement_fires(self, price_movement_packet, analysis_event_id) -> None:
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            price_movement_packet,
            analysis_event_id=analysis_event_id,
        )

        assert len(firings) >= 1
        firing_ids = [f.rule_id for f in firings]
        assert "price_movement_v1" in firing_ids

    def test_evaluate_volume_spike_fires(self, volume_spike_packet, analysis_event_id) -> None:
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            volume_spike_packet,
            analysis_event_id=analysis_event_id,
        )

        assert len(firings) >= 1
        firing_ids = [f.rule_id for f in firings]
        assert "volume_spike_v1" in firing_ids

    def test_evaluate_breakout_fires(self, breakout_packet, analysis_event_id) -> None:
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            breakout_packet,
            analysis_event_id=analysis_event_id,
        )

        assert len(firings) >= 1
        firing_ids = [f.rule_id for f in firings]
        assert "breakout_v1" in firing_ids

    def test_evaluate_multi_rule_fire(self, multi_fire_packet, analysis_event_id) -> None:
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            multi_fire_packet,
            analysis_event_id=analysis_event_id,
        )

        fired_rules = {f.rule_id for f in firings}
        assert "price_movement_v1" in fired_rules
        assert "volume_spike_v1" in fired_rules
        assert "breakout_v1" in fired_rules

    def test_evaluate_no_fire_returns_empty(self, no_fire_packet, analysis_event_id) -> None:
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            no_fire_packet,
            analysis_event_id=analysis_event_id,
        )

        assert len(firings) == 0

    def test_stale_packet_returns_empty(self, stale_packet, analysis_event_id) -> None:
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            stale_packet,
            analysis_event_id=analysis_event_id,
        )

        assert len(firings) == 0

    def test_evaluate_stores_execution(self, price_movement_packet, analysis_event_id) -> None:
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            price_movement_packet,
            analysis_event_id=analysis_event_id,
        )

        assert len(firings) > 0
        for firing in firings:
            execution = RuleExecution.objects.get(
                analysis_event_id=analysis_event_id,
                rule_id=firing.rule_id,
            )
            assert execution.symbol == firing.symbol
            assert execution.severity == firing.severity.value

    def test_idempotent_evaluation_does_not_duplicate_executions(
        self, price_movement_packet, analysis_event_id
    ) -> None:
        service = RuleEvaluationService()

        first_firings = service.evaluate_enriched_packet(
            price_movement_packet,
            analysis_event_id=analysis_event_id,
        )
        second_firings = service.evaluate_enriched_packet(
            price_movement_packet,
            analysis_event_id=analysis_event_id,
        )

        assert len(first_firings) >= 1
        assert len(second_firings) == 0

        for firing in first_firings:
            executions = RuleExecution.objects.filter(
                analysis_event_id=analysis_event_id,
                rule_id=firing.rule_id,
            )
            assert executions.count() == 1

    def test_firing_carries_correct_metadata(
        self, price_movement_packet, analysis_event_id
    ) -> None:
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            price_movement_packet,
            analysis_event_id=analysis_event_id,
        )

        assert len(firings) >= 1
        firing = next(f for f in firings if f.rule_id == "price_movement_v1")
        assert firing.analysis_event_id == analysis_event_id
        assert firing.symbol == "RELIANCE"
        assert "change_pct" in firing.trigger_data
        assert firing.occurred_at is not None

    def test_regime_is_injected_into_firing_trigger_data(
        self, price_movement_packet, analysis_event_id
    ) -> None:
        price_movement_packet = replace(
            price_movement_packet,
            packet=_with_regime(price_movement_packet.packet, "BULLISH"),
        )
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            price_movement_packet,
            analysis_event_id=analysis_event_id,
        )

        assert len(firings) >= 1
        for firing in firings:
            assert firing.trigger_data["regime"] == "BULLISH"

    def test_regime_absent_omits_key_from_trigger_data(
        self, price_movement_packet, analysis_event_id
    ) -> None:
        from core.execution_context import bind_account_override

        # This test only cares about trigger_data shape, not the go/no-go gate.
        # A live no-regime packet is correctly fail-closed by ADR-029, so run
        # under replay semantics (bound override) to isolate trigger_data.
        regime_free = replace(
            price_movement_packet,
            packet=_with_regime(price_movement_packet.packet, None),
        )
        service = RuleEvaluationService()
        with bind_account_override(uuid.uuid4()):
            firings = service.evaluate_enriched_packet(
                regime_free,
                analysis_event_id=analysis_event_id,
            )

        assert len(firings) >= 1
        for firing in firings:
            assert "regime" not in firing.trigger_data

    def test_publish_rule_firing_publishes_domain_event(
        self, price_movement_packet, analysis_event_id
    ) -> None:
        reset_event_bus()
        bus = get_event_bus()

        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            price_movement_packet,
            analysis_event_id=analysis_event_id,
        )

        assert len(firings) >= 1
        firing = firings[0]

        published_id = service.publish_rule_firing(firing)

        assert published_id is not None
        assert len(bus.published_events) >= 1
        published_types = [e.event_type for e in bus.published_events]
        assert "rule_engine.RuleFired" in published_types

        fired_event = next(e for e in bus.published_events if e.event_type == "rule_engine.RuleFired")
        assert fired_event.payload["rule_id"] == firing.rule_id
        assert fired_event.payload["symbol"] == firing.symbol
        assert fired_event.payload["event_type"] == firing.event_type
        assert fired_event.payload["severity"] == firing.severity.value
        assert fired_event.payload["analysis_event_id"] == str(analysis_event_id)
        assert fired_event.correlation_id == analysis_event_id

    def test_publish_rule_firing_marks_execution_as_published(
        self, price_movement_packet, analysis_event_id
    ) -> None:
        reset_event_bus()
        get_event_bus()

        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            price_movement_packet,
            analysis_event_id=analysis_event_id,
        )

        assert len(firings) >= 1
        firing = firings[0]

        published_id = service.publish_rule_firing(firing)

        execution = RuleExecution.objects.get(
            analysis_event_id=analysis_event_id,
            rule_id=firing.rule_id,
        )
        assert execution.published_event_id == published_id

    def test_publish_rule_firing_raises_on_bus_failure(
        self, price_movement_packet, analysis_event_id, monkeypatch
    ) -> None:
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            price_movement_packet,
            analysis_event_id=analysis_event_id,
        )
        assert len(firings) >= 1
        firing = firings[0]

        def _broken_bus():
            raise RuntimeError("Redis is down")

        monkeypatch.setattr(
            "apps.rule_engine.application.rule_evaluation_service.get_event_bus",
            _broken_bus,
        )

        with pytest.raises(RuleEvaluationError):
            service.publish_rule_firing(firing)

    def test_evaluate_returns_firings_with_correct_event_type(
        self, volume_spike_packet, analysis_event_id
    ) -> None:
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            volume_spike_packet,
            analysis_event_id=analysis_event_id,
        )

        volume_firings = [f for f in firings if f.rule_id == "volume_spike_v1"]
        assert len(volume_firings) == 1
        assert volume_firings[0].event_type == "volume_spike"

    def test_evaluate_breakout_trigger_data(
        self, breakout_packet, analysis_event_id
    ) -> None:
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            breakout_packet,
            analysis_event_id=analysis_event_id,
        )

        breakout_firings = [f for f in firings if f.rule_id == "breakout_v1"]
        assert len(breakout_firings) == 1
        trigger = breakout_firings[0].trigger_data
        assert "bb_upper_break" in trigger
        assert "resistance_break" in trigger

    def test_high_beta_breakout_is_registered_and_discoverable(self) -> None:
        service = RuleEvaluationService()
        rule_ids = [r.rule_id for r in service._registry.get_registered_rules()]

        assert "high_beta_breakout_v1" in rule_ids

    def test_short_breakdown_is_registered_and_discoverable(self) -> None:
        service = RuleEvaluationService()
        rule_ids = [r.rule_id for r in service._registry.get_registered_rules()]

        assert "short_breakdown_v1" in rule_ids
