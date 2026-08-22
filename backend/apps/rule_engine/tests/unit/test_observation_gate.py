"""LIVE-PAPER-DRESS-REHEARSAL-1 — paper-only observation bypass of ADR-029 gate.

An owner-flagged ``ObservedRule`` lets an unvalidated (rule, regime) fire on
the PAPER broker so the drift monitor has live data. Fail-closed everywhere
else: no observation row, symbol-scoped mismatch, disabled config, or
``BROKER_ENVIRONMENT=live`` must keep the old gating verdicts.

These tests deliberately do NOT bind an account override — a bound override is
the backtest-replay bypass (fires ungated by design), which would mask the
live-path behaviour under test here.
"""

from __future__ import annotations

import pytest

from apps.live_drift.infrastructure.models import ObservedRule
from apps.rule_engine.application.rule_evaluation_service import RuleEvaluationService

pytestmark = pytest.mark.django_db


def _flag(rule_id: str = "price_movement_v1", regime: str = "BULLISH", symbol: str = "") -> None:
    """Observation row + enabled-but-unvalidated RuleConfig.

    The observation list never relieves the operator of creating/enabling the
    RuleConfig itself (ADR-029 §3's explicit human decision); it only waives
    the per-regime validation verdict, on paper.
    """
    from apps.rule_engine.infrastructure.models import RuleConfig

    ObservedRule.objects.create(
        rule_id=rule_id,
        regime=regime,
        symbol=symbol,
        baseline_expectancy=None,
        enabled=True,
    )
    RuleConfig.objects.create(rule_id=rule_id, enabled=True, validated_regimes={})


def _evaluate(packet, analysis_event_id) -> list:
    return RuleEvaluationService().evaluate_enriched_packet(
        packet, analysis_event_id=analysis_event_id
    )


class TestObservationPaperBypass:
    def test_observed_combo_fires_without_validated_regimes(
        self, price_movement_packet, analysis_event_id
    ) -> None:
        _flag()
        firings = _evaluate(price_movement_packet, analysis_event_id)
        assert len(firings) == 1
        assert firings[0].rule_id == "price_movement_v1"

    def test_symbol_scoped_observation_blocks_other_symbols(
        self, price_movement_packet, analysis_event_id
    ) -> None:
        packet_symbol = price_movement_packet.packet.symbol
        _flag(symbol="TCS" if packet_symbol != "TCS" else "INFY")
        firings = _evaluate(price_movement_packet, analysis_event_id)
        assert firings == []

    def test_symbol_scoped_observation_allows_matching_symbol(
        self, price_movement_packet, analysis_event_id
    ) -> None:
        packet_symbol = price_movement_packet.packet.symbol
        _flag(symbol=packet_symbol)
        firings = _evaluate(price_movement_packet, analysis_event_id)
        assert len(firings) == 1

    def test_live_environment_refuses_bypass(
        self, price_movement_packet, analysis_event_id, settings
    ) -> None:
        _flag()
        settings.BROKER_ENVIRONMENT = "live"
        assert _evaluate(price_movement_packet, analysis_event_id) == []

    def test_disabled_observation_row_does_not_bypass(
        self, price_movement_packet, analysis_event_id
    ) -> None:
        _flag()
        ObservedRule.objects.update(enabled=False)
        assert _evaluate(price_movement_packet, analysis_event_id) == []

    def test_no_observation_still_gated(
        self, price_movement_packet, analysis_event_id
    ) -> None:
        assert _evaluate(price_movement_packet, analysis_event_id) == []

