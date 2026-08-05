"""Exponential Moving Average (EMA) indicator."""

from decimal import Decimal
from typing import Any

import numpy as np

from apps.technical_analysis.indicators.base import (
    IndicatorConfig,
    IndicatorResult,
    IndicatorType,
    OHLCV,
    SingleValueIndicator,
    validate_period,
)
from apps.technical_analysis.indicators.exceptions import InvalidParameterError


class EMAConfig(IndicatorConfig):
    """Configuration for EMA indicator."""

    def __init__(
        self,
        name: str = "ema",
        period: int = 20,
        source: str = "close",
        smoothing: float = 2.0,
        **kwargs,
    ) -> None:
        period = validate_period(period, "period", max_period=1000)
        if smoothing <= 0:
            raise InvalidParameterError("Smoothing must be > 0", parameter_name="smoothing", parameter_value=smoothing)
        super().__init__(
            name=name,
            indicator_type=IndicatorType.TREND,
            parameters={"period": period, "source": source, "smoothing": smoothing},
            required_data_points=period,
        )

    @property
    def period(self) -> int:
        return self.parameters["period"]

    @property
    def source(self) -> str:
        return self.parameters["source"]

    @property
    def smoothing(self) -> float:
        return self.parameters["smoothing"]


class EMAIndicator(SingleValueIndicator[Decimal]):
    """Exponential Moving Average (EMA) indicator.

    EMA = (Close - Previous EMA) * Multiplier + Previous EMA
    Multiplier = Smoothing / (Period + 1)
    """

    def __init__(self, config: EMAConfig) -> None:
        super().__init__(config)

    @property
    def config(self) -> EMAConfig:
        return self._config

    def _validate_config(self) -> None:
        super()._validate_config()
        if self.config.period < 1:
            raise InvalidParameterError(
                "EMA period must be >= 1",
                parameter_name="period",
                parameter_value=self.config.period,
            )
        valid_sources = {"open", "high", "low", "close", "hl2", "hlc3", "ohlc4"}
        if self.config.source not in valid_sources:
            raise InvalidParameterError(
                f"Invalid source '{self.config.source}'. Must be one of {valid_sources}",
                parameter_name="source",
                parameter_value=self.config.source,
            )

    def _get_source_values(self, data) -> np.ndarray:
        """Get source values as numpy array."""
        source = self.config.source
        if source == "open":
            return data.get_opens()
        elif source == "high":
            return data.get_highs()
        elif source == "low":
            return data.get_lows()
        elif source == "close":
            return data.get_closes()
        elif source == "hl2":
            return (data.get_highs() + data.get_lows()) / 2
        elif source == "hlc3":
            return (data.get_highs() + data.get_lows() + data.get_closes()) / 3
        elif source == "ohlc4":
            return (data.get_opens() + data.get_highs() + data.get_lows() + data.get_closes()) / 4
        return data.get_closes()

    def _calculate_single(self, data, index: int) -> Decimal:
        values = self._get_source_values(data)
        period = self.config.period
        smoothing = self.config.smoothing
        alpha = smoothing / (period + 1)

        if index == period - 1:
            return Decimal(str(np.mean(values[:period])))

        prev_ema = self._calculate_single(data, index - 1)
        return Decimal(str(values[index] * alpha + float(prev_ema) * (1 - alpha)))


def calculate_ema(values: list[Decimal] | np.ndarray, period: int, smoothing: float = 2.0) -> list[Decimal]:
    """Standalone EMA calculation."""
    arr = np.array([float(v) for v in values], dtype=np.float64)
    if len(arr) < period:
        return []
    alpha = smoothing / (period + 1)
    result = np.full(len(arr), np.nan)
    result[period - 1] = np.mean(arr[:period])
    for i in range(period, len(arr)):
        result[i] = arr[i] * alpha + result[i - 1] * (1 - alpha)
    return [Decimal(str(v)) if not np.isnan(v) else Decimal("NaN") for v in result]


EMA = EMAIndicator
EMAConfig = EMAConfig