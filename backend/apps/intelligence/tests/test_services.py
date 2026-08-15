from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from apps.intelligence.domain.market_regime import MarketRegime, MultiTimeframeAlignment
from apps.intelligence.services import MarketContextService
from apps.macro_context.domain.entities import MacroContext
from core.events.event_types import (
    BreadthContext,
    CircuitStatus,
    DataQuality,
    IntelligencePacket,
    NewsContext,
    PriceContext,
    TechnicalContext,
)


def _make_packet() -> IntelligencePacket:
    return IntelligencePacket(
        symbol="RELIANCE",
        timestamp=datetime.now(timezone.utc),
        freshness_validated=True,
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
            ema_20=Decimal("2485.00"),
            ema_50=Decimal("2450.00"),
            ema_200=Decimal("2380.00"),
            atr_14=Decimal("45.0"),
        ),
        breadth_context=BreadthContext(
            sector_index_change_pct=Decimal("0.45"),
            sector_advance_decline=Decimal("0.30"),
            nifty_change_pct=Decimal("0.25"),
            sensex_change_pct=Decimal("0.20"),
        ),
        news_context=NewsContext(),
        data_quality=DataQuality(quality_score=0.95),
    )


def _sparse_packet() -> IntelligencePacket:
    """Sparse packet: confidence is unclamped (0.8) so the macro term moves it."""
    return IntelligencePacket(
        symbol="RELIANCE",
        timestamp=datetime.now(timezone.utc),
        freshness_validated=True,
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
        data_quality=DataQuality(quality_score=0.8),
    )


class TestMarketContextService:
    @override_settings(MARKET_CONTEXT_SCORING_ENABLED=True)
    def test_build_signal_context_populates_new_fields_when_enabled(self) -> None:
        service = MarketContextService()
        with patch.object(service, "_get_pine_outputs") as mock_pine:
            mock_pine.return_value = {"1D": {}, "4h": {}, "1h": {}}
            context = service.build_signal_context(
                symbol="RELIANCE",
                packet=_make_packet(),
            )

        assert hasattr(context, "bullishness_score")
        assert hasattr(context, "bearishness_score")
        assert hasattr(context, "volatility_score")
        assert hasattr(context, "trend_score")
        assert hasattr(context, "liquidity_score")
        assert hasattr(context, "momentum_score")
        assert hasattr(context, "overall_context_confidence")
        assert hasattr(context, "pattern_alignment_note")

        assert 0.0 <= context.bullishness_score <= 1.0
        assert 0.0 <= context.bearishness_score <= 1.0
        assert 0.0 <= context.volatility_score <= 1.0
        assert 0.0 <= context.trend_score <= 1.0
        assert 0.0 <= context.liquidity_score <= 1.0
        assert 0.0 <= context.momentum_score <= 1.0
        assert 0.0 <= context.overall_context_confidence <= 1.0
        assert context.pattern_alignment_note == "PATTERN_ENGINE_NOT_AVAILABLE"

    @override_settings(MARKET_CONTEXT_SCORING_ENABLED=True)
    def test_build_signal_context_regime_and_mtf_unchanged(self) -> None:
        service = MarketContextService()
        with patch.object(service, "_get_pine_outputs") as mock_pine:
            mock_pine.return_value = {"1D": {}, "4h": {}, "1h": {}}
            context = service.build_signal_context(
                symbol="RELIANCE",
                packet=_make_packet(),
            )

        assert context.market_regime is not None
        assert context.multi_timeframe_alignment is not None
        assert context.sector_context != ""
        assert context.data_quality_note != ""

    @override_settings(MARKET_CONTEXT_SCORING_ENABLED=False)
    def test_build_signal_context_defaults_when_disabled(self) -> None:
        service = MarketContextService()
        with patch.object(service, "_get_pine_outputs") as mock_pine:
            mock_pine.return_value = {"1D": {}, "4h": {}, "1h": {}}
            context = service.build_signal_context(
                symbol="RELIANCE",
                packet=_make_packet(),
            )

        assert context.bullishness_score == 0.0
        assert context.bearishness_score == 0.0
        assert context.volatility_score == 0.0
        assert context.trend_score == 0.0
        assert context.liquidity_score == 0.0
        assert context.momentum_score == 0.0
        assert context.overall_context_confidence == 0.0
        assert context.pattern_alignment_note == "SCORING_DISABLED"

    @override_settings(MARKET_CONTEXT_SCORING_ENABLED=True)
    def test_existing_fields_unchanged_when_scoring_added(self) -> None:
        service = MarketContextService()
        with patch.object(service, "_get_pine_outputs") as mock_pine:
            mock_pine.return_value = {"1D": {}, "4h": {}, "1h": {}}
            context = service.build_signal_context(
                symbol="RELIANCE",
                packet=_make_packet(),
            )

        assert context.symbol == "RELIANCE"
        assert context.market_regime in MarketRegime
        assert context.multi_timeframe_alignment in MultiTimeframeAlignment
        assert isinstance(context.pine_outputs, dict)
        assert isinstance(context.news_headlines, list)
        assert isinstance(context.sector_context, str)
        assert isinstance(context.event_data, dict)
        assert isinstance(context.data_quality_note, str)

    @override_settings(MARKET_CONTEXT_SCORING_ENABLED=True)
    def test_macro_context_forwarded_into_scoring(self) -> None:
        # MACRO-CONTEXT-SCORING-1 integration: the packet's macro_context must
        # reach compute_context_scores via the ContextScoringInput forward.
        # Sparse packet: conf(None) = 0.8, conf(series_count=4) = 1.8/2.0 = 0.9.
        service = MarketContextService()
        with patch.object(service, "_get_pine_outputs") as mock_pine:
            mock_pine.return_value = {"1D": {}, "4h": {}, "1h": {}}
            base_context = service.build_signal_context(
                symbol="RELIANCE",
                packet=_sparse_packet(),
            )

        macro_packet = dataclasses.replace(
            _sparse_packet(),
            macro_context=MacroContext(
                as_of=datetime(2025, 1, 15, tzinfo=timezone.utc),
                dgs10=Decimal("4.20"),
                fedfunds=Decimal("4.00"),
                cpiaucsl=Decimal("3.50"),
                t10y2y=Decimal("-0.20"),
                series_count=4,
            ),
        )
        service = MarketContextService()
        with patch.object(service, "_get_pine_outputs") as mock_pine:
            mock_pine.return_value = {"1D": {}, "4h": {}, "1h": {}}
            macro_context = service.build_signal_context(
                symbol="RELIANCE",
                packet=macro_packet,
            )

        assert base_context.overall_context_confidence == 0.8
        assert macro_context.overall_context_confidence == 0.9
        assert macro_context.overall_context_confidence > base_context.overall_context_confidence
