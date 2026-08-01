from __future__ import annotations

from apps.ai_engine.services import ConfidenceEngine

engine = ConfidenceEngine()


class TestPatternConfidenceContribution:
    def test_contribution_is_additive(self) -> None:
        result = engine.evaluate(
            raw_confidence=0.60,
            pattern_confidence_contribution=0.20,
        )
        assert result.adjusted_confidence == 0.80
        assert any("pattern confidence contribution: +0.2000" in r for r in result.adjustment_reasons)

    def test_contribution_clamps_at_one(self) -> None:
        result = engine.evaluate(
            raw_confidence=0.90,
            pattern_confidence_contribution=0.50,
        )
        assert result.adjusted_confidence == 1.00

    def test_zero_contribution_is_noop(self) -> None:
        result = engine.evaluate(
            raw_confidence=0.60,
            pattern_confidence_contribution=0.0,
        )
        assert result.adjusted_confidence == 0.60
        assert not any("pattern confidence contribution" in r for r in result.adjustment_reasons)


class TestPatternAccuracyPenalty:
    def test_accuracy_above_floor_no_penalty(self) -> None:
        result = engine.evaluate(
            raw_confidence=0.60,
            pattern_historical_accuracy=0.80,
        )
        assert result.adjusted_confidence == 0.60
        assert not any("pattern accuracy penalty" in r for r in result.adjustment_reasons)

    def test_accuracy_below_floor_applies_percentage_penalty(self) -> None:
        result = engine.evaluate(
            raw_confidence=0.60,
            pattern_historical_accuracy=0.40,
        )
        assert result.adjusted_confidence == 0.55
        assert any("pattern accuracy penalty: accuracy=0.4000, penalty=0.0500" in r for r in result.adjustment_reasons)

    def test_accuracy_penalty_caps_at_zero(self) -> None:
        result = engine.evaluate(
            raw_confidence=0.05,
            pattern_historical_accuracy=0.00,
        )
        assert result.adjusted_confidence == 0.00


class TestPatternFeedCombined:
    def test_both_terms_apply_in_order(self) -> None:
        result = engine.evaluate(
            raw_confidence=0.60,
            pattern_confidence_contribution=0.20,
            pattern_historical_accuracy=0.40,
        )
        assert result.adjusted_confidence == 0.75
        assert any("pattern confidence contribution" in r for r in result.adjustment_reasons)
        assert any("pattern accuracy penalty" in r for r in result.adjustment_reasons)

    def test_none_inputs_match_no_feed_behavior(self) -> None:
        no_feed = engine.evaluate(raw_confidence=0.60)
        feed_none = engine.evaluate(
            raw_confidence=0.60,
            pattern_confidence_contribution=None,
            pattern_historical_accuracy=None,
        )
        assert feed_none.adjusted_confidence == no_feed.adjusted_confidence
        assert feed_none.adjustment_reasons == no_feed.adjustment_reasons

    def test_threshold_logic_unaffected_by_pattern_feed(self) -> None:
        strategy = type(
            "Strategy",
            (),
            {"confidence_threshold": 0.70},
        )()
        result = engine.evaluate(
            raw_confidence=0.65,
            strategy=strategy,
            pattern_confidence_contribution=0.20,
        )
        assert result.threshold_met is False
        assert result.adjusted_confidence == 0.85
