"""
TradeVision AI — Market Regime Detection.

Deterministic, rule-based market regime classification. No AI involvement.

Regime is detected from Pine Script indicator values and market data.
This runs before any AI call and provides the AI with regime context.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any


class MarketRegime(str, Enum):
    """Current market regime classification — determined by rule-based logic."""

    BULLISH = "BULLISH"
    """Price above key EMAs, RSI bullish, MACD positive, sector positive."""

    BEARISH = "BEARISH"
    """Price below key EMAs, RSI bearish, MACD negative, sector negative."""

    RANGING = "RANGING"
    """Price between support/resistance, neutral RSI, low ATR."""

    VOLATILE = "VOLATILE"
    """Elevated ATR (>1.5x 20d avg) or India VIX > 20."""

    BREAKOUT = "BREAKOUT"
    """Price breaks above resistance with above-average volume."""

    BREAKDOWN = "BREAKDOWN"
    """Price breaks below support with above-average volume."""


class MultiTimeframeAlignment(str, Enum):
    """Alignment of trend across daily, 4-hour, and 1-hour timeframes."""

    BULLISH_ALIGNED = "BULLISH_ALIGNED"
    """All three timeframes show bullish trend."""

    BEARISH_ALIGNED = "BEARISH_ALIGNED"
    """All three timeframes show bearish trend."""

    CONFLICTING = "CONFLICTING"
    """Timeframes disagree on trend direction."""

    NEUTRAL = "NEUTRAL"
    """No clear trend on any timeframe."""


@dataclass(frozen=True)
class RegimeInput:
    """Input data for regime detection — sourced from Pine Script output."""

    current_price: Decimal
    ema_20: Decimal | None
    ema_50: Decimal | None
    ema_200: Decimal | None
    rsi_14: Decimal | None
    macd: Decimal | None
    macd_histogram: Decimal | None
    bb_upper: Decimal | None
    bb_lower: Decimal | None
    atr_14: Decimal | None
    avg_atr_20d: Decimal | None
    volume_ratio: float
    india_vix: Decimal | None
    sector_change_pct: Decimal | None
    support_levels: tuple[Decimal, ...]
    resistance_levels: tuple[Decimal, ...]


@dataclass(frozen=True)
class RegimeOutput:
    """Output of regime detection — regime + supporting evidence."""

    regime: MarketRegime
    primary_reason: str
    supporting_evidence: tuple[str, ...]


def detect_regime(inputs: RegimeInput) -> RegimeOutput:
    """Determine the current market regime using deterministic rules.

    Args:
        inputs: Pine Script indicator values and market data.

    Returns:
        RegimeOutput with the detected regime and supporting evidence.
    """
    evidence: list[str] = []

    if inputs.rsi_14 is not None and inputs.bb_upper is not None and inputs.bb_lower is not None:
        rsi = float(inputs.rsi_14)
        price = float(inputs.current_price)
        bb_upper = float(inputs.bb_upper)
        bb_lower = float(inputs.bb_lower)

        if price > bb_upper and inputs.volume_ratio >= 1.5:
            evidence.append(f"Price {price} broke above upper BB {bb_upper} with {inputs.volume_ratio}x volume")
            return RegimeOutput(
                regime=MarketRegime.BREAKOUT,
                primary_reason="Price broke above upper Bollinger Band with above-average volume",
                supporting_evidence=tuple(evidence),
            )

        if price < bb_lower and inputs.volume_ratio >= 1.5:
            evidence.append(f"Price {price} broke below lower BB {bb_lower} with {inputs.volume_ratio}x volume")
            return RegimeOutput(
                regime=MarketRegime.BREAKDOWN,
                primary_reason="Price broke below lower Bollinger Band with above-average volume",
                supporting_evidence=tuple(evidence),
            )

    if inputs.atr_14 is not None and inputs.avg_atr_20d is not None:
        atr_ratio = float(inputs.atr_14) / float(inputs.avg_atr_20d)
        if atr_ratio > 1.5:
            evidence.append(f"ATR ratio {atr_ratio:.2f}x exceeds 1.5x threshold")

    if inputs.india_vix is not None and float(inputs.india_vix) > 20:
        evidence.append(f"India VIX at {float(inputs.india_vix):.1f} exceeds 20 threshold")
        if len(evidence) > 0:
            return RegimeOutput(
                regime=MarketRegime.VOLATILE,
                primary_reason=f"Elevated volatility: ATR ratio {atr_ratio:.2f}x, VIX {float(inputs.india_vix):.1f}",
                supporting_evidence=tuple(evidence),
            )

    if inputs.ema_50 is not None and inputs.ema_200 is not None:
        price = float(inputs.current_price)
        ema_50 = float(inputs.ema_50)
        ema_200 = float(inputs.ema_200)
        rsi = float(inputs.rsi_14) if inputs.rsi_14 is not None else 50

        if price > ema_50 and price > ema_200 and rsi > 55:
            evidence.append(f"Price {price} > EMA50 {ema_50} > EMA200 {ema_200}, RSI {rsi:.0f}")
            if inputs.macd is not None and inputs.macd_histogram is not None:
                if float(inputs.macd) > 0 and float(inputs.macd_histogram) > 0:
                    evidence.append(f"MACD positive ({inputs.macd}), histogram expanding ({inputs.macd_histogram})")
            if inputs.sector_change_pct is not None and float(inputs.sector_change_pct) > 0:
                evidence.append(f"Sector up {float(inputs.sector_change_pct):.1f}%")
            return RegimeOutput(
                regime=MarketRegime.BULLISH,
                primary_reason="Price above key EMAs with bullish RSI and positive momentum",
                supporting_evidence=tuple(evidence),
            )

        if price < ema_50 and price < ema_200 and rsi < 45:
            evidence.append(f"Price {price} < EMA50 {ema_50} < EMA200 {ema_200}, RSI {rsi:.0f}")
            if inputs.macd is not None and inputs.macd_histogram is not None:
                if float(inputs.macd) < 0 and float(inputs.macd_histogram) < 0:
                    evidence.append(f"MACD negative ({inputs.macd}), histogram contracting ({inputs.macd_histogram})")
            if inputs.sector_change_pct is not None and float(inputs.sector_change_pct) < 0:
                evidence.append(f"Sector down {float(inputs.sector_change_pct):.1f}%")
            return RegimeOutput(
                regime=MarketRegime.BEARISH,
                primary_reason="Price below key EMAs with bearish RSI and negative momentum",
                supporting_evidence=tuple(evidence),
            )

    evidence.append(f"Price between support/resistance, RSI {float(inputs.rsi_14 or 50):.0f}")
    return RegimeOutput(
        regime=MarketRegime.RANGING,
        primary_reason="No clear directional signal — price in neutral zone",
        supporting_evidence=tuple(evidence),
    )


def detect_mtf_alignment(
    daily_trend: str,
    hourly_trend: str,
    four_hour_trend: str,
) -> MultiTimeframeAlignment:
    """Determine multi-timeframe alignment from individual timeframe trends.

    Args:
        daily_trend: Trend direction on daily timeframe ("UP"/"DOWN"/"SIDEWAYS").
        hourly_trend: Trend direction on 1-hour timeframe.
        four_hour_trend: Trend direction on 4-hour timeframe.

    Returns:
        MultiTimeframeAlignment value.
    """
    trends: list[str] = [daily_trend, four_hour_trend, hourly_trend]
    up_count = trends.count("UP")
    down_count = trends.count("DOWN")

    if up_count == 3:
        return MultiTimeframeAlignment.BULLISH_ALIGNED
    if down_count == 3:
        return MultiTimeframeAlignment.BEARISH_ALIGNED
    if up_count >= 2 or down_count >= 2:
        return MultiTimeframeAlignment.CONFLICTING
    return MultiTimeframeAlignment.NEUTRAL
