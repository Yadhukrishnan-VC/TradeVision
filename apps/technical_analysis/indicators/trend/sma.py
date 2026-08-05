"""Simple Moving Average (SMA) indicator."""

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


class SMAConfig(IndicatorConfig):
    """Configuration for SMA indicator."""

    def __init__(
        self,
        name: str = "sma",
        period: int = 20,
        source: str = "close",
        **kwargs,
    ) -> None:
        period = validate_period(period, "period", max_period=1000)
        super().__init__(
            name=name,
            indicator_type=IndicatorType.TREND,
            parameters={"period": period, "source": source},
            required_data_points=period,
        )

    @property
    def period(self) -> int:
        return self.parameters["period"]

    @property
    def source(self) -> str:
        return self.parameters["source"]


class SMAIndicator(SingleValueIndicator[Decimal]):
    """Simple Moving Average (SMA) indicator.

    SMA = Sum(close prices over period) / period
    """

    def __init__(self, config: SMAConfig) -> None:
        super().__init__(config)

    @property
    def config(self) -> SMAConfig:
        return self._config

    def _validate_config(self) -> None:
        super()._validate_config()
        if self.config.period < 1:
            raise InvalidParameterError(
                "SMA period must be >= 1",
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
        start = index - period + 1
        window = values[start : index + 1]
        return Decimal(str(np.mean(window)))


def calculate_sma(values: list[Decimal] | np.ndarray, period: int) -> list[Decimal]:
    """Standalone SMA calculation."""
    arr = np.array([float(v) for v in values], dtype=np.float64)
    if len(arr) < period:
        return []
    result = np.full(len(arr), np.nan)
    for i in range(period - 1, len(arr)):
        result[i] = np.mean(arr[i - period + 1 : i + 1])
    return [Decimal(str(v)) if not np.isnan(v) else Decimal("NaN") for v in result]


SMA = SMAIndicator
SMAConfig = SMAConfig