from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import dataclasses

from apps.intelligence.domain.context_scoring import (
    ContextScoringInput,
    compute_context_scores,
)
from apps.intelligence.domain.market_regime import MarketRegime, MultiTimeframeAlignment
from apps.macro_context.domain.entities import MacroContext
from core.events.event_types import (
    BreadthContext,
    CircuitStatus,
    DataQuality,
    NewsContext,
    PatternContext,
    PatternMatch,
    PriceContext,
    TechnicalContext,
)


def _full_packet_input() -> ContextScoringInput:
    return ContextScoringInput(
        price_context=PriceContext(
            current_price=Decimal("2500.00"),
            open_price=Decimal("2480.00"),
            high=Decimal("2520.00"),
            low=Decimal("2470.00"),
            volume=2000000,
            avg_volume_20d=1000000,
            circuit_status=CircuitStatus.NORMAL,
            prev_close=Decimal("2480.00"),
            change_pct=Decimal("0.81"),
        ),
        technical_context=TechnicalContext(
            trend="UPTREND",
            rsi_14=Decimal("62.5"),
            macd=Decimal("12.5"),
            macd_signal=Decimal("10.2"),
            macd_histogram=Decimal("2.3"),
            bb_upper=Decimal("2600.00"),
            bb_lower=Decimal("2400.00"),
            bb_width=Decimal("200.00"),
            vwap=Decimal("2490.00"),
            atr_14=Decimal("45.0"),
            ema_20=Decimal("2485.00"),
            ema_50=Decimal("2450.00"),
            ema_200=Decimal("2380.00"),
            support_levels=(Decimal("2450.00"), Decimal("2400.00")),
            resistance_levels=(Decimal("2550.00"), Decimal("2600.00")),
        ),
        breadth_context=BreadthContext(
            sector_index_change_pct=Decimal("0.45"),
            sector_advance_decline=Decimal("0.30"),
            nifty_change_pct=Decimal("0.25"),
            sensex_change_pct=Decimal("0.20"),
        ),
        news_context=NewsContext(),
        regime=MarketRegime.BULLISH,
        mtf_alignment=MultiTimeframeAlignment.BULLISH_ALIGNED,
        global_context=None,
        pattern_context=None,
        data_quality=DataQuality(quality_score=0.95),
    )


def _sparse_packet_input() -> ContextScoringInput:
    """Sparse fixture: no technical series, no volume, avg_volume_20d == 0.

    Keeps ``overall_context_confidence`` unclamped (0.8) so the macro
    arithmetic below is exact and hand-verifiable.
    """
    return ContextScoringInput(
        price_context=PriceContext(
            current_price=Decimal("100.00"),
            open_price=Decimal("99.00"),
            high=Decimal("101.00"),
            low=Decimal("98.00"),
            volume=50000,
            avg_volume_20d=0,
            circuit_status=CircuitStatus.NORMAL,
        ),
        technical_context=TechnicalContext(),
        breadth_context=BreadthContext(
            sector_index_change_pct=Decimal("0.00"),
            sector_advance_decline=Decimal("0.00"),
            nifty_change_pct=Decimal("0.00"),
            sensex_change_pct=Decimal("0.00"),
        ),
        news_context=NewsContext(),
        regime=MarketRegime.RANGING,
        mtf_alignment=MultiTimeframeAlignment.NEUTRAL,
        data_quality=DataQuality(quality_score=0.8),
    )


def _macro(series_count: int) -> MacroContext:
    """Build a MacroContext with ``series_count`` known series populated."""
    series = (Decimal("4.20"), Decimal("4.00"), Decimal("3.50"), Decimal("-0.20"))
    values = series[:series_count]
    return MacroContext(
        as_of=datetime(2025, 1, 15, tzinfo=timezone.utc),
        dgs10=values[0] if len(values) > 0 else None,
        fedfunds=values[1] if len(values) > 1 else None,
        cpiaucsl=values[2] if len(values) > 2 else None,
        t10y2y=values[3] if len(values) > 3 else None,
        series_count=series_count,
    )


class TestContextScoring:
    def test_full_packet_all_scores_in_range(self) -> None:
        result = compute_context_scores(_full_packet_input())

        assert 0.0 <= result.bullishness_score <= 1.0
        assert 0.0 <= result.bearishness_score <= 1.0
        assert 0.0 <= result.volatility_score <= 1.0
        assert 0.0 <= result.trend_score <= 1.0
        assert 0.0 <= result.liquidity_score <= 1.0
        assert 0.0 <= result.momentum_score <= 1.0
        assert 0.0 <= result.overall_context_confidence <= 1.0

    def test_bullish_packet_high_bullish_low_bearish(self) -> None:
        result = compute_context_scores(_full_packet_input())
        assert result.bullishness_score > result.bearishness_score
        assert result.bullishness_score > 0.5

    def test_minimal_packet_scores_computed_no_exception(self) -> None:
        inputs = ContextScoringInput(
            price_context=PriceContext(
                current_price=Decimal("100.00"),
                open_price=Decimal("99.00"),
                high=Decimal("101.00"),
                low=Decimal("98.00"),
                volume=50000,
                avg_volume_20d=0,
                circuit_status=CircuitStatus.NORMAL,
            ),
            technical_context=TechnicalContext(),
            breadth_context=BreadthContext(
                sector_index_change_pct=Decimal("0.00"),
                sector_advance_decline=Decimal("0.00"),
                nifty_change_pct=Decimal("0.00"),
                sensex_change_pct=Decimal("0.00"),
            ),
            news_context=NewsContext(),
            regime=MarketRegime.RANGING,
            mtf_alignment=MultiTimeframeAlignment.NEUTRAL,
        )
        result = compute_context_scores(inputs)
        assert 0.0 <= result.bullishness_score <= 1.0
        assert 0.0 <= result.overall_context_confidence <= 1.0

    def test_pattern_context_none_uses_sentinel(self) -> None:
        inputs = _full_packet_input()
        result = compute_context_scores(inputs)
        assert result.pattern_alignment_note == "PATTERN_ENGINE_NOT_AVAILABLE"

    def test_pattern_context_present_uses_summary(self) -> None:
        inputs = dataclasses.replace(
            _full_packet_input(),
            pattern_context=PatternContext(
                similar_dates=(
                    PatternMatch(
                        date_str="2024-03-17",
                        similarity_score=Decimal("0.85"),
                        outcome_summary="Price rose 2%",
                    ),
                ),
                top_analogue_summary="Similar to 2024-03-17: price rose 2%",
            ),
        )
        result = compute_context_scores(inputs)
        assert result.pattern_alignment_note == "Similar to 2024-03-17: price rose 2%"

    def test_pattern_context_empty_summary_falls_back_to_sentinel(self) -> None:
        inputs = dataclasses.replace(
            _full_packet_input(),
            pattern_context=PatternContext(),
        )
        result = compute_context_scores(inputs)
        assert result.pattern_alignment_note == "PATTERN_ENGINE_NOT_AVAILABLE"

    def test_extreme_rsi_clamps_scores(self) -> None:
        tc = TechnicalContext(
            rsi_14=Decimal("0"),
            macd=Decimal("-10"),
            macd_histogram=Decimal("-5"),
            ema_50=Decimal("100"),
            ema_200=Decimal("100"),
        )
        inputs = ContextScoringInput(
            price_context=PriceContext(
                current_price=Decimal("50"),
                open_price=Decimal("55"),
                high=Decimal("56"),
                low=Decimal("49"),
                volume=100000,
                avg_volume_20d=50000,
                circuit_status=CircuitStatus.NORMAL,
            ),
            technical_context=tc,
            breadth_context=BreadthContext(
                sector_index_change_pct=Decimal("-0.50"),
                sector_advance_decline=Decimal("-0.30"),
                nifty_change_pct=Decimal("-0.40"),
                sensex_change_pct=Decimal("-0.35"),
            ),
            news_context=NewsContext(),
            regime=MarketRegime.BEARISH,
            mtf_alignment=MultiTimeframeAlignment.BEARISH_ALIGNED,
        )
        result = compute_context_scores(inputs)
        assert result.bearishness_score > result.bullishness_score
        assert result.momentum_score < 0.5

    def test_bullish_and_bearish_not_simple_complements(self) -> None:
        ranging_inputs = ContextScoringInput(
            price_context=PriceContext(
                current_price=Decimal("100.00"),
                open_price=Decimal("100.00"),
                high=Decimal("101.00"),
                low=Decimal("99.00"),
                volume=50000,
                avg_volume_20d=50000,
                circuit_status=CircuitStatus.NORMAL,
            ),
            technical_context=TechnicalContext(),
            breadth_context=BreadthContext(
                sector_index_change_pct=Decimal("0.00"),
                sector_advance_decline=Decimal("0.00"),
                nifty_change_pct=Decimal("0.00"),
                sensex_change_pct=Decimal("0.00"),
            ),
            news_context=NewsContext(),
            regime=MarketRegime.RANGING,
            mtf_alignment=MultiTimeframeAlignment.NEUTRAL,
        )
        result = compute_context_scores(ranging_inputs)
        assert result.bullishness_score + result.bearishness_score < 1.5

    def test_zero_volume_does_not_raise(self) -> None:
        inputs = ContextScoringInput(
            price_context=PriceContext(
                current_price=Decimal("100.00"),
                open_price=Decimal("99.00"),
                high=Decimal("101.00"),
                low=Decimal("98.00"),
                volume=0,
                avg_volume_20d=0,
                circuit_status=CircuitStatus.NORMAL,
            ),
            technical_context=TechnicalContext(),
            breadth_context=BreadthContext(
                sector_index_change_pct=Decimal("0.00"),
                sector_advance_decline=Decimal("0.00"),
                nifty_change_pct=Decimal("0.00"),
                sensex_change_pct=Decimal("0.00"),
            ),
            news_context=NewsContext(),
            regime=MarketRegime.RANGING,
            mtf_alignment=MultiTimeframeAlignment.NEUTRAL,
        )
        result = compute_context_scores(inputs)
        assert 0.0 <= result.liquidity_score <= 1.0

    def test_all_none_optional_fields_no_exception(self) -> None:
        inputs = ContextScoringInput(
            price_context=PriceContext(
                current_price=Decimal("100.00"),
                open_price=Decimal("99.00"),
                high=Decimal("101.00"),
                low=Decimal("98.00"),
                volume=50000,
                avg_volume_20d=0,
                circuit_status=CircuitStatus.NORMAL,
            ),
            technical_context=TechnicalContext(
                rsi_14=None, macd=None, macd_histogram=None,
                bb_upper=None, bb_lower=None, ema_20=None,
                ema_50=None, ema_200=None, atr_14=None,
            ),
            breadth_context=BreadthContext(
                sector_index_change_pct=Decimal("0.00"),
                sector_advance_decline=Decimal("0.00"),
                nifty_change_pct=Decimal("0.00"),
                sensex_change_pct=Decimal("0.00"),
            ),
            news_context=NewsContext(),
            regime=MarketRegime.RANGING,
            mtf_alignment=MultiTimeframeAlignment.NEUTRAL,
        )
        result = compute_context_scores(inputs)
        assert result.bullishness_score >= 0.0
        assert result.overall_context_confidence >= 0.0

    def test_data_quality_degradation_lowers_confidence(self) -> None:
        full = _full_packet_input()
        high_conf = compute_context_scores(full)

        degraded = dataclasses.replace(
            full,
            data_quality=DataQuality(
                quality_score=0.5,
                missing_sources=("news", "options"),
                stale_sources=("technical",),
            ),
        )
        low_conf = compute_context_scores(degraded)

        assert low_conf.overall_context_confidence < high_conf.overall_context_confidence

    def test_momentum_neutral_at_center(self) -> None:
        tc = TechnicalContext(
            rsi_14=Decimal("50"),
            macd=Decimal("0"),
            macd_histogram=Decimal("0"),
            ema_20=Decimal("100.00"),
        )
        inputs = ContextScoringInput(
            price_context=PriceContext(
                current_price=Decimal("100.00"),
                open_price=Decimal("100.00"),
                high=Decimal("101.00"),
                low=Decimal("99.00"),
                volume=50000,
                avg_volume_20d=50000,
                circuit_status=CircuitStatus.NORMAL,
            ),
            technical_context=tc,
            breadth_context=BreadthContext(
                sector_index_change_pct=Decimal("0.00"),
                sector_advance_decline=Decimal("0.00"),
                nifty_change_pct=Decimal("0.00"),
                sensex_change_pct=Decimal("0.00"),
            ),
            news_context=NewsContext(),
            regime=MarketRegime.RANGING,
            mtf_alignment=MultiTimeframeAlignment.NEUTRAL,
        )
        result = compute_context_scores(inputs)
        assert 0.3 <= result.momentum_score <= 0.7

    def test_zero_current_price_with_atr_does_not_raise(self) -> None:
        inputs = ContextScoringInput(
            price_context=PriceContext(
                current_price=Decimal("0"),
                open_price=Decimal("0"),
                high=Decimal("0"),
                low=Decimal("0"),
                volume=50000,
                avg_volume_20d=100000,
                circuit_status=CircuitStatus.NORMAL,
            ),
            technical_context=TechnicalContext(
                atr_14=Decimal("45.0"),
            ),
            breadth_context=BreadthContext(
                sector_index_change_pct=Decimal("0.00"),
                sector_advance_decline=Decimal("0.00"),
                nifty_change_pct=Decimal("0.00"),
                sensex_change_pct=Decimal("0.00"),
            ),
            news_context=NewsContext(),
            regime=MarketRegime.RANGING,
            mtf_alignment=MultiTimeframeAlignment.NEUTRAL,
        )
        result = compute_context_scores(inputs)
        assert 0.0 <= result.volatility_score <= 1.0

    def test_zero_ema_50_with_ema_20_does_not_raise(self) -> None:
        inputs = ContextScoringInput(
            price_context=PriceContext(
                current_price=Decimal("100.00"),
                open_price=Decimal("99.00"),
                high=Decimal("101.00"),
                low=Decimal("98.00"),
                volume=50000,
                avg_volume_20d=50000,
                circuit_status=CircuitStatus.NORMAL,
            ),
            technical_context=TechnicalContext(
                ema_20=Decimal("100.00"),
                ema_50=Decimal("0"),
            ),
            breadth_context=BreadthContext(
                sector_index_change_pct=Decimal("0.00"),
                sector_advance_decline=Decimal("0.00"),
                nifty_change_pct=Decimal("0.00"),
                sensex_change_pct=Decimal("0.00"),
            ),
            news_context=NewsContext(),
            regime=MarketRegime.RANGING,
            mtf_alignment=MultiTimeframeAlignment.NEUTRAL,
        )
        result = compute_context_scores(inputs)
        assert 0.0 <= result.trend_score <= 1.0

    def test_zero_ema_200_with_ema_50_does_not_raise(self) -> None:
        inputs = ContextScoringInput(
            price_context=PriceContext(
                current_price=Decimal("100.00"),
                open_price=Decimal("99.00"),
                high=Decimal("101.00"),
                low=Decimal("98.00"),
                volume=50000,
                avg_volume_20d=50000,
                circuit_status=CircuitStatus.NORMAL,
            ),
            technical_context=TechnicalContext(
                ema_50=Decimal("100.00"),
                ema_200=Decimal("0"),
            ),
            breadth_context=BreadthContext(
                sector_index_change_pct=Decimal("0.00"),
                sector_advance_decline=Decimal("0.00"),
                nifty_change_pct=Decimal("0.00"),
                sensex_change_pct=Decimal("0.00"),
            ),
            news_context=NewsContext(),
            regime=MarketRegime.RANGING,
            mtf_alignment=MultiTimeframeAlignment.NEUTRAL,
        )
        result = compute_context_scores(inputs)
        assert 0.0 <= result.trend_score <= 1.0

    def test_macro_context_none_confidence_byte_for_byte_regression(self) -> None:
        # Byte-for-byte regression guard: with macro_context absent the
        # confidence must equal the pre-MACRO-CONTEXT-SCORING-1 value for
        # otherwise-identical inputs (the existing suite fixture included).
        full = compute_context_scores(_full_packet_input())
        sparse = compute_context_scores(_sparse_packet_input())
        assert full.overall_context_confidence == 1.0
        assert sparse.overall_context_confidence == 0.8

    def test_macro_context_full_series_raises_confidence(self) -> None:
        # All 4 tracked series known (series_count=4):
        # conf = (0.8 + 4 / 4.0) / (1.0 + 1.0) = 1.8 / 2.0 = 0.9.
        base = _sparse_packet_input()
        base_confidence = compute_context_scores(base).overall_context_confidence
        with_macro = compute_context_scores(
            dataclasses.replace(base, macro_context=_macro(series_count=4))
        )
        assert with_macro.overall_context_confidence == 0.9
        assert with_macro.overall_context_confidence > base_confidence

    def test_macro_context_empty_series_dilutes_confidence(self) -> None:
        # series_count=0 (built but no known values): the term adds weight 1.0
        # with zero signal, so confidence drops by hand-computation:
        # conf = (0.8 + 0 / 4.0) / (1.0 + 1.0) = 0.8 / 2.0 = 0.4. This is the
        # explicit consequence of the formula and is asserted as-is.
        with_macro = compute_context_scores(
            dataclasses.replace(_sparse_packet_input(), macro_context=_macro(series_count=0))
        )
        assert with_macro.overall_context_confidence == 0.4

    def test_macro_context_variants_leave_directional_scores_unchanged(self) -> None:
        none_result = compute_context_scores(_sparse_packet_input())
        for series_count in (0, 4):
            variant_result = compute_context_scores(
                dataclasses.replace(
                    _sparse_packet_input(),
                    macro_context=_macro(series_count=series_count),
                )
            )
            for score_name in (
                "bullishness_score",
                "bearishness_score",
                "volatility_score",
                "trend_score",
                "liquidity_score",
                "momentum_score",
            ):
                assert getattr(variant_result, score_name) == getattr(none_result, score_name)
