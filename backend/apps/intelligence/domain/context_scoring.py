from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from apps.intelligence.domain.market_regime import MarketRegime, MultiTimeframeAlignment
from core.events.event_types import (
    BreadthContext,
    DataQuality,
    GlobalContext,
    NewsContext,
    PatternContext,
    PriceContext,
    TechnicalContext,
)


@dataclass(frozen=True)
class ContextScoringInput:
    price_context: PriceContext
    technical_context: TechnicalContext
    breadth_context: BreadthContext
    news_context: NewsContext
    regime: MarketRegime
    mtf_alignment: MultiTimeframeAlignment
    global_context: GlobalContext | None = None
    pattern_context: PatternContext | None = None
    data_quality: DataQuality = DataQuality()


@dataclass(frozen=True)
class ContextScoringOutput:
    bullishness_score: float
    bearishness_score: float
    volatility_score: float
    trend_score: float
    liquidity_score: float
    momentum_score: float
    overall_context_confidence: float
    pattern_alignment_note: str


def _to_float(value: Decimal | None) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def compute_context_scores(inputs: ContextScoringInput) -> ContextScoringOutput:
    pc = inputs.price_context
    tc = inputs.technical_context
    bc = inputs.breadth_context
    nc = inputs.news_context
    dq = inputs.data_quality
    regime = inputs.regime
    mtf = inputs.mtf_alignment

    rsi = _to_float(tc.rsi_14)
    macd = _to_float(tc.macd)
    macd_hist = _to_float(tc.macd_histogram)
    ema_50 = _to_float(tc.ema_50)
    ema_200 = _to_float(tc.ema_200)
    price = _to_float(pc.current_price)
    bb_upper = _to_float(tc.bb_upper)
    bb_lower = _to_float(tc.bb_lower)
    atr_14 = _to_float(tc.atr_14)

    # --- bullishness_score (0-1) ---
    bullish_signals = 0.0
    bull_weight = 0.0

    if tc.rsi_14 is not None:
        bull_weight += 1.0
        if rsi > 60:
            bullish_signals += 1.0
        elif rsi > 50:
            bullish_signals += 0.5

    if tc.macd is not None and tc.macd_histogram is not None:
        bull_weight += 1.0
        if macd > 0 and macd_hist > 0:
            bullish_signals += 1.0
        elif macd > 0:
            bullish_signals += 0.5

    if tc.ema_50 is not None and tc.ema_200 is not None:
        bull_weight += 1.0
        if price > ema_50 and price > ema_200:
            bullish_signals += 1.0
        elif price > ema_50 or price > ema_200:
            bullish_signals += 0.5

    bull_weight += 1.0
    if regime in (MarketRegime.BULLISH, MarketRegime.BREAKOUT):
        bullish_signals += 1.0
    elif regime == MarketRegime.RANGING:
        bullish_signals += 0.3

    if bc.sector_index_change_pct is not None:
        bull_weight += 0.5
        if float(bc.sector_index_change_pct) > 0:
            bullish_signals += 0.5

    bullishness_score = _clamp(bullish_signals / bull_weight if bull_weight > 0 else 0.0)

    # --- bearishness_score (0-1) ---
    bearish_signals = 0.0
    bear_weight = 0.0

    if tc.rsi_14 is not None:
        bear_weight += 1.0
        if rsi < 40:
            bearish_signals += 1.0
        elif rsi < 50:
            bearish_signals += 0.5

    if tc.macd is not None and tc.macd_histogram is not None:
        bear_weight += 1.0
        if macd < 0 and macd_hist < 0:
            bearish_signals += 1.0
        elif macd < 0:
            bearish_signals += 0.5

    if tc.ema_50 is not None and tc.ema_200 is not None:
        bear_weight += 1.0
        if price < ema_50 and price < ema_200:
            bearish_signals += 1.0
        elif price < ema_50 or price < ema_200:
            bearish_signals += 0.5

    bear_weight += 1.0
    if regime in (MarketRegime.BEARISH, MarketRegime.BREAKDOWN):
        bearish_signals += 1.0
    elif regime == MarketRegime.RANGING:
        bearish_signals += 0.3

    if bc.sector_index_change_pct is not None:
        bear_weight += 0.5
        if float(bc.sector_index_change_pct) < 0:
            bearish_signals += 0.5

    bearishness_score = _clamp(bearish_signals / bear_weight if bear_weight > 0 else 0.0)

    # --- volatility_score (0-1) ---
    vol_signals = 0.0
    vol_weight = 0.0

    if tc.atr_14 is not None:
        vol_weight += 1.0
        if atr_14 > 0:
            if pc.avg_volume_20d > 0:
                atr_to_avg = atr_14 / float(pc.current_price) * 100
                vol_signals += _clamp(atr_to_avg / 3.0)
            else:
                vol_signals += 0.5

    if tc.bb_upper is not None and tc.bb_lower is not None:
        vol_weight += 1.0
        bb_range = bb_upper - bb_lower
        if bb_range > 0 and price > 0:
            bb_width_pct = bb_range / price
            vol_signals += _clamp(bb_width_pct / 0.1)

    if inputs.global_context is not None:
        india_vix = _to_float(inputs.global_context.india_vix)
        vol_weight += 1.0
        if india_vix > 25:
            vol_signals += 1.0
        elif india_vix > 20:
            vol_signals += 0.6
        elif india_vix > 15:
            vol_signals += 0.3

    vol_weight += 1.0
    if regime == MarketRegime.VOLATILE:
        vol_signals += 1.0

    volatility_score = _clamp(vol_signals / vol_weight if vol_weight > 0 else 0.0)

    # --- trend_score (0-1, direction-agnostic strength) ---
    trend_signals = 0.0
    trend_weight = 0.0

    if tc.ema_20 is not None and tc.ema_50 is not None:
        trend_weight += 1.0
        ema_gap = abs(_to_float(tc.ema_20) - ema_50) / ema_50
        trend_signals += _clamp(ema_gap * 5.0)

    if tc.ema_50 is not None and tc.ema_200 is not None:
        trend_weight += 1.0
        ema_gap = abs(ema_50 - ema_200) / ema_200
        trend_signals += _clamp(ema_gap * 5.0)

    if tc.rsi_14 is not None:
        trend_weight += 1.0
        trend_signals += _clamp(abs(rsi - 50) / 50.0)

    trend_weight += 1.0
    if mtf in (MultiTimeframeAlignment.BULLISH_ALIGNED, MultiTimeframeAlignment.BEARISH_ALIGNED):
        trend_signals += 1.0
    elif mtf == MultiTimeframeAlignment.CONFLICTING:
        trend_signals += 0.6

    trend_score = _clamp(trend_signals / trend_weight if trend_weight > 0 else 0.0)

    # --- liquidity_score (0-1) ---
    vol_ratio = (
        pc.volume / pc.avg_volume_20d
        if pc.avg_volume_20d > 0
        else 0.0
    )
    liquidity_score = _clamp(vol_ratio / 2.0 if vol_ratio < 2.0 else 1.0)

    # --- momentum_score (0-1, 0.5 = neutral) ---
    momentum_raw = 0.5

    if tc.rsi_14 is not None:
        momentum_raw += (rsi - 50) / 100.0

    if tc.macd_histogram is not None:
        momentum_raw += _clamp(abs(macd_hist) / 5.0) * (1.0 if macd_hist > 0 else -1.0) * 0.3

    if tc.ema_20 is not None:
        ema_20 = _to_float(tc.ema_20)
        if ema_20 > 0:
            price_vs_ema = (price - ema_20) / ema_20
            momentum_raw += _clamp(price_vs_ema * 3.0)

    momentum_score = _clamp(momentum_raw)

    # --- overall_context_confidence (0-1) ---
    conf_signals = 0.0
    conf_weight = 0.0

    conf_weight += 1.0
    conf_signals += dq.quality_score

    if tc.rsi_14 is not None:
        conf_weight += 1.0
        conf_signals += 1.0

    if tc.macd is not None:
        conf_weight += 1.0
        conf_signals += 1.0

    if tc.ema_20 is not None and tc.ema_50 is not None:
        conf_weight += 1.0
        conf_signals += 1.0

    if pc.avg_volume_20d > 0:
        conf_weight += 0.5
        conf_signals += 1.0

    if dq.missing_sources:
        conf_signals -= 0.3 * min(len(dq.missing_sources), 3)

    if dq.stale_sources:
        conf_signals -= 0.2 * min(len(dq.stale_sources), 3)

    overall_context_confidence = _clamp(conf_signals / conf_weight if conf_weight > 0 else dq.quality_score)

    # --- pattern_alignment_note ---
    if inputs.pattern_context is not None:
        pattern_alignment_note = inputs.pattern_context.top_analogue_summary or "PATTERN_ENGINE_NOT_AVAILABLE"
    else:
        pattern_alignment_note = "PATTERN_ENGINE_NOT_AVAILABLE"

    return ContextScoringOutput(
        bullishness_score=bullishness_score,
        bearishness_score=bearishness_score,
        volatility_score=volatility_score,
        trend_score=trend_score,
        liquidity_score=liquidity_score,
        momentum_score=momentum_score,
        overall_context_confidence=overall_context_confidence,
        pattern_alignment_note=pattern_alignment_note,
    )
