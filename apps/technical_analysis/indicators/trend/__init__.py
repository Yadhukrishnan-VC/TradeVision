"""Trend indicators package."""

from apps.technical_analysis.indicators.trend.adx import ADXIndicator, calculate_adx, calculate_dm, calculate_di
from apps.technical_analysis.indicators.trend.ema import EMAIndicator, calculate_ema
from apps.technical_analysis.indicators.trend.macd import MACDIndicator, calculate_macd
from apps.technical_analysis.indicators.trend.sma import SMAIndicator, calculate_sma

__all__ = [
    "SMAIndicator",
    "EMAIndicator",
    "MACDIndicator",
    "ADXIndicator",
    "calculate_sma",
    "calculate_ema",
    "calculate_macd",
    "calculate_adx",
    "calculate_dm",
    "calculate_di",
]

from apps.technical_analysis.indicators.registry import register_indicator
from apps.technical_analysis.indicators.base import IndicatorType

register_indicator(SMAIndicator, "sma", IndicatorType.TREND, {"period": 20})
register_indicator(EMAIndicator, "ema", IndicatorType.TREND, {"period": 20})
register_indicator(MACDIndicator, "macd", IndicatorType.TREND, {"fast_period": 12, "slow_period": 26, "signal_period": 9})
register_indicator(ADXIndicator, "adx", IndicatorType.TREND, {"period": 14})