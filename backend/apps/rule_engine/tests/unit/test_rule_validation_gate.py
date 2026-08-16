"""ADR-029 — go/no-go validation gate enforcement tests.

Covers the fail-closed filter (per exclusion reason + pass-through) and the
safety-critical replay bypass: backtest replay (account override bound) must
always fire ungated, while live firing (no override) is gated. The integration
verdict (BULLISH GO fires / RANGING not validated does not) lives here too.
"""

from __future__ import annotations

import uuid

import pytest

from apps.rule_engine.application.rule_evaluation_service import RuleEvaluationService
from apps.rule_engine.infrastructure.models import RuleConfig
from core.execution_context import bind_account_override

pytestmark = pytest.mark.django_db


def _make_gated(
    *,
    enabled: bool = True,
    regime: str = "BULLISH",
    status: str = "GO",
) -> None:
    from apps.rule_engine.infrastructure.repositories import RuleConfigRepository

    config = RuleConfig(
        rule_id="price_movement_v1",
        enabled=enabled,
        validated_regimes={regime: {"status": status}},
    )
    RuleConfigRepository().create(config)


class TestFilterGateExclusions:
    def test_no_config_is_gated_out(self, price_movement_packet, analysis_event_id) -> None:
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            price_movement_packet,
            analysis_event_id=analysis_event_id,
        )
        assert firings == []
        assert RuleConfig.objects.count() == 0

    def test_disabled_config_is_gated_out(
        self, price_movement_packet, analysis_event_id
    ) -> None:
        _make_gated(enabled=False)
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            price_movement_packet,
            analysis_event_id=analysis_event_id,
        )
        assert firings == []

    def test_no_regime_is_gated_out(self, price_movement_packet, analysis_event_id) -> None:
        _make_gated()
        from dataclasses import replace

        regime_free = replace(
            price_movement_packet,
            packet=replace(price_movement_packet.packet, regime=None),
        )
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            regime_free,
            analysis_event_id=analysis_event_id,
        )
        assert firings == []

    def test_other_regime_not_validated_is_gated_out(
        self, price_movement_packet, analysis_event_id
    ) -> None:
        _make_gated(regime="BEARISH", status="GO")
        from dataclasses import replace

        ranging = replace(
            price_movement_packet,
            packet=replace(price_movement_packet.packet, regime="RANGING"),
        )
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            ranging,
            analysis_event_id=analysis_event_id,
        )
        assert firings == []

    def test_no_go_verdict_is_gated_out(
        self, price_movement_packet, analysis_event_id
    ) -> None:
        _make_gated(status="NO_GO")
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            price_movement_packet,
            analysis_event_id=analysis_event_id,
        )
        assert firings == []

    def test_insufficient_data_verdict_is_gated_out(
        self, price_movement_packet, analysis_event_id
    ) -> None:
        _make_gated(status="INSUFFICIENT_DATA")
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            price_movement_packet,
            analysis_event_id=analysis_event_id,
        )
        assert firings == []

    def test_go_verdict_passes_through(
        self, price_movement_packet, analysis_event_id
    ) -> None:
        _make_gated(status="GO")
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            price_movement_packet,
            analysis_event_id=analysis_event_id,
        )
        assert len(firings) >= 1
        assert any(f.rule_id == "price_movement_v1" for f in firings)


class TestReplayBypass:
    def test_bound_override_fires_without_any_config(
        self, price_movement_packet, analysis_event_id
    ) -> None:
        """Safety-critical: replay with no RuleConfig rows still fires."""
        service = RuleEvaluationService()
        with bind_account_override(uuid.uuid4()):
            firings = service.evaluate_enriched_packet(
                price_movement_packet,
                analysis_event_id=analysis_event_id,
            )
        assert len(firings) >= 1
        assert RuleConfig.objects.count() == 0

    def test_unbound_live_fires_nothing_without_config(
        self, price_movement_packet, analysis_event_id
    ) -> None:
        """Safety-critical: live firing without validation is fail-closed."""
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            price_movement_packet,
            analysis_event_id=analysis_event_id,
        )
        assert firings == []


class TestLiveIntegrationVerdict:
    def test_bullish_go_fires_live(self, price_movement_packet, analysis_event_id) -> None:
        _make_gated(status="GO")
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            price_movement_packet,
            analysis_event_id=analysis_event_id,
        )
        assert len(firings) >= 1

    def test_ranging_not_validated_does_not_fire_live(
        self, price_movement_packet, analysis_event_id
    ) -> None:
        _make_gated(status="GO")  # only BULLISH is validated
        from dataclasses import replace

        ranging = replace(
            price_movement_packet,
            packet=replace(price_movement_packet.packet, regime="RANGING"),
        )
        service = RuleEvaluationService()
        firings = service.evaluate_enriched_packet(
            ranging,
            analysis_event_id=analysis_event_id,
        )
        assert firings == []