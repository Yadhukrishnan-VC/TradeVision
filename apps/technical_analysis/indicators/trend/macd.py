from __future__ import annotations

from decimal import Decimal
from typing import Any

import numpy as np

from apps.technical_analysis.indicators.base import (
    IndicatorConfig,
    IndicatorResult,
    IndicatorType,
    MultiValueIndicator,
    validate_period,
)
from apps.technical_analysis.indicators.exceptions import InvalidParameterError
from apps.technical_analysis.indicators.trend.ema import EMA, EMAConfig


class MACDConfig(IndicatorConfig):
    """Configuration for MACD indicator."""

    def __init__(
        self,
        name: str = "macd",
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        source: str = "close",
        **kwargs,
    ) -> None:
        fast_period = validate_period(fast_period, "fast_period", max_period=500)
        slow_period = validate_period(slow_period, "slow_period", max_period=500)
        signal_period = validate_period(signal_period, "signal_period", max_period=500)

        if fast_period >= slow_period:
            raise InvalidParameterError(
                "fast_period must be < slow_period",
                parameter_name="fast_period",
                parameter_value=fast_period,
                valid_range=(1, slow_period - 1),
            )

        required = slow_period + signal_period - 1

        super().__init__(
            name=name,
            indicator_type=IndicatorType.TREND,
            parameters={
                "fast_period": fast_period,
                "slow_period": slow_period,
                "signal_period": signal_period,
                "source": source,
            },
            required_data_points=required,
        )

    @property
    def fast_period(self) -> int:
        return self.parameters["fast_period"]

    @property
    def slow_period(self) -> int:
        return self.parameters["slow_period"]

    @property
    def signal_period(self) -> int:
        return self.parameters["signal_period"]

    @property
    def source(self) -> str:
        return self.parameters["source"]


class MACD(MultiValueIndicator[tuple[Decimal, Decimal, Decimal]]):
    """Moving Average Convergence Divergence (MACD).

    MACD Line = Fast EMA - Slow EMA
    Signal Line = EMA of MACD Line (signal_period)
    Histogram = MACD Line - Signal Line
    """

    INDICATOR_TYPE = IndicatorType.TREND

    def __init__(self, config: MACDConfig) -> None:
        super().__init__(config)
        self._fast_ema: EMA | None = None
        self._slow_ema: EMA | None = None
        self._signal_ema: EMA | None = None

    @property
    def config(self) -> MACDConfig:
        return self._config

    @property
    def output_names(self) -> tuple[str, ...]:
        return ("macd", "signal", "histogram")

    def _validate_config(self) -> None:
        super()._validate_config()
        if self.config.fast_period >= self.config.slow_period:
            raise InvalidParameterError(
                "fast_period must be < slow_period",
                parameter_name="fast_period",
                parameter_value=self.config.fast_period,
            )

    def _get_source_array(self, data) -> np.ndarray:
        source = self.config.source
        if source == "open":
            return data.get_opens()
        elif source == "high":
            return data.get_highs()
        elif source == "low":
            return data.get_lows()
        elif source == "typical":
            highs = data.get_highs()
            lows = data.get_lows()
            closes = data.get_closes()
            return (highs + lows + closes) / 3
        elif source == "median":
            highs = data.get_highs()
            lows = data.get_lows()
            return (highs + lows) / 2
        elif source == "weighted":
            highs = data.get_highs()
            lows = data.get_lows()
            closes = data.get_closes()
            return (highs + lows + 2 * closes) / 4
        return data.get_closes()

    def _initialize_emas(self) -> None:
        """Initialize EMA indicators."""
        fast_config = EMAConfig(
            name=f"{self.name}_fast",
            period=self.config.fast_period,
            source=self.config.source,
        )
        slow_config = EMAConfig(
            name=f"{self.name}_slow",
            period=self.config.slow_period,
            source=self.config.source,
        )
        signal_config = EMAConfig(
            name=f"{self.name}_signal",
            period=self.config.signal_period,
            source="close",
        )
        self._fast_ema = EMA(fast_config)
        self._slow_ema = EMA(slow_config)
        self._signal_ema = EMA(signal_config)

    def _calculate_single(self, data, index: int) -> tuple[Decimal, Decimal, Decimal]:
        if self._fast_ema is None:
            self._initialize_emas()

        source_array = self._get_source_array(data)

        if index < self.required_data_points - 1:
            return (Decimal("NaN"), Decimal("NaN"), Decimal("NaN"))

        fast_ema = self._fast_ema.get_latest(data.slice(index - self.config.fast_period + 1, index + 1))
        slow_ema = self._slow_ema.get_latest(data.slice(index - self.config.slow_period + 1, index + 1))

        if fast_ema is None or slow_ema is None:
            return (Decimal("NaN"), Decimal("NaN"), Decimal("NaN"))

        macd_line = fast_ema.value - slow_ema.value

        signal_data = self._get_macd_series(data, index)
        if len(signal_data) >= self.config.signal_period:
            signal_ema = self._signal_ema.get_latest(signal_data)
            signal_line = signal_ema.value if signal_ema else Decimal("NaN")
        else:
            signal_line = Decimal("NaN")

        histogram = macd_line - signal_line if not signal_line.is_nan() else Decimal("NaN")

        return (macd_line, signal_line, histogram)

    def _get_macd_series(self, data, index: int):
        """Get MACD series up to index for signal calculation."""
        from apps.technical_analysis.indicators.base import IndicatorData

        macd_values = []
        for i in range(self.config.slow_period - 1, index + 1):
            fast_ema = self._fast_ema.get_latest(
                data.slice(i - self.config.fast_period + 1, i + 1)
            )
            slow_ema = self._slow_ema.get_latest(
                data.slice(i - self.config.slow_period + 1, i + 1)
            )
            if fast_ema and slow_ema:
                macd_values.append(fast_ema.value - slow_ema.value)

        if not macd_values:
            return IndicatorData([], "", data.timeframe)

        ohlcv_list = []
        for i, val in enumerate(macd_values):
            ts = data.ohlcv[self.config.slow_period - 1 + i].timestamp
            ohlcv_list.append(
                type("OHLCV", (), {"timestamp": ts, "close": val, "volume": 0, "open": val, "high": val, "low": val})
            )

        return IndicatorData(ohlcv=ohlcv_list, symbol=data.symbol, timeframe=data.timeframe)

    def _calculate(self, data) -> list[IndicatorResult[tuple[Decimal, Decimal, Decimal]]]:
        results = []
        for i in range(self.required_data_points - 1, len(data)):
            macd, signal, histogram = self._calculate_single(data, i)
            results.append(
                IndicatorResult(
                    name=self.name,
                    indicator_type=self.indicator_type,
                    timestamp=data[i].timestamp,
                    value=(macd, signal, histogram),
                    parameters=self.config.parameters,
                    metadata={"output_names": self.output_names},
                )
            )
        return results


def calculate_macd(
    closes: list[Decimal] | np.ndarray,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[list[Decimal], list[Decimal], list[Decimal]]:
    """Standalone MACD calculation."""
    from apps.technical_analysis.indicators.trend.ema import calculate_ema

    arr = np.array([float(v) for v in closes], dtype=np.float64)
    if len(arr) < slow_period + signal_period - 1:
        return [], [], []

    fast_ema = calculate_ema(arr, fast_period)
    slow_ema = calculate_ema(arr, slow_period)

    min_len = min(len(fast_ema), len(slow_ema))
    macd = [fast_ema[i] - slow_ema[i] for i in range(min_len)]

    macd_floats = [float(v) for v in macd]
    signal = calculate_ema(macd_floats, signal_period)

    histogram = []
    for i in range(len(macd)):
        if i < len(signal):
            histogram.append(macd[i] - signal[i])
        else:
            histogram.append(Decimal("NaN"))

    return macd, signal, histogram