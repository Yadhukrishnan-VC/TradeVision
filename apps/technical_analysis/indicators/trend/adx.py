"""Average Directional Index (ADX) indicator."""

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


class ADXConfig(IndicatorConfig):
    """Configuration for ADX indicator."""

    def __init__(
        self,
        name: str = "adx",
        period: int = 14,
        smoothing: int = 14,
        **kwargs,
    ) -> None:
        period = validate_period(period, "period", max_period=500)
        smoothing = validate_period(smoothing, "smoothing", max_period=500)
        super().__init__(
            name=name,
            indicator_type=IndicatorType.TREND,
            parameters={"period": period, "smoothing": smoothing},
            required_data_points=period + smoothing,
        )

    @property
    def period(self) -> int:
        return self.parameters["period"]

    @property
    def smoothing(self) -> int:
        return self.parameters["smoothing"]


class ADX(MultiValueIndicator[tuple[Decimal, Decimal, Decimal]]):
    """Average Directional Index (ADX) indicator.

    Outputs: (adx, plus_di, minus_di)
    """

    INDICATOR_TYPE = IndicatorType.TREND

    def __init__(self, config: ADXConfig) -> None:
        super().__init__(config)

    @property
    def config(self) -> ADXConfig:
        return self._config

    @property
    def output_names(self) -> tuple[str, str, str]:
        return ("adx", "plus_di", "minus_di")

    def _validate_config(self) -> None:
        super()._validate_config()
        if self.config.period < 1:
            raise InvalidParameterError(
                "ADX period must be >= 1",
                parameter_name="period",
                parameter_value=self.config.period,
            )
        if self.config.smoothing < 1:
            raise InvalidParameterError(
                "ADX smoothing must be >= 1",
                parameter_name="smoothing",
                parameter_value=self.config.smoothing,
            )

    def _calculate_single(self, data, index: int) -> tuple[Decimal, Decimal, Decimal]:
        period = self.config.period
        smoothing = self.config.smoothing
        highs = data.get_highs()
        lows = data.get_lows()
        closes = data.get_closes()

        if index < period:
            return (Decimal("NaN"), Decimal("NaN"), Decimal("NaN"))

        tr_values = np.zeros(len(highs))
        plus_dm = np.zeros(len(highs))
        minus_dm = np.zeros(len(highs))

        for i in range(1, len(highs)):
            tr_values[i] = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            high_diff = highs[i] - highs[i - 1]
            low_diff = lows[i - 1] - lows[i]
            if high_diff > low_diff and high_diff > 0:
                plus_dm[i] = high_diff
            if low_diff > high_diff and low_diff > 0:
                minus_dm[i] = low_diff

        atr = self._wilder_smoothing(tr_values, period)
        plus_di_raw = self._wilder_smoothing(plus_dm, period)
        minus_di_raw = self._wilder_smoothing(minus_dm, period)

        plus_di = np.zeros(len(highs))
        minus_di = np.zeros(len(highs))
        for i in range(len(highs)):
            if atr[i] > 0:
                plus_di[i] = 100 * plus_di_raw[i] / atr[i]
                minus_di[i] = 100 * minus_di_raw[i] / atr[i]

        dx = np.zeros(len(highs))
        for i in range(len(highs)):
            di_sum = plus_di[i] + minus_di[i]
            if di_sum > 0:
                dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / di_sum

        adx = self._wilder_smoothing(dx, smoothing)

        return (
            Decimal(str(adx[index])),
            Decimal(str(plus_di[index])),
            Decimal(str(minus_di[index])),
        )

    def _wilder_smoothing(self, values: np.ndarray, period: int) -> np.ndarray:
        """Wilder's smoothing (similar to EMA with alpha = 1/period)."""
        result = np.zeros(len(values))
        if len(values) < period:
            return result

        result[period - 1] = np.mean(values[:period])
        alpha = 1.0 / period
        for i in range(period, len(values)):
            result[i] = values[i] * alpha + result[i - 1] * (1 - alpha)
        return result


def calculate_adx(
    highs: list[Decimal] | np.ndarray,
    lows: list[Decimal] | np.ndarray,
    closes: list[Decimal] | np.ndarray,
    period: int = 14,
    smoothing: int = 14,
) -> tuple[list[Decimal], list[Decimal], list[Decimal]]:
    """Standalone ADX calculation."""
    h = np.array([float(v) for v in highs], dtype=np.float64)
    l = np.array([float(v) for v in lows], dtype=np.float64)
    c = np.array([float(v) for v in closes], dtype=np.float64)

    if len(h) < period + smoothing:
        return [], [], []

    tr = np.zeros(len(h))
    plus_dm = np.zeros(len(h))
    minus_dm = np.zeros(len(h))

    for i in range(1, len(h)):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        hd = h[i] - h[i - 1]
        ld = l[i - 1] - l[i]
        if hd > ld and hd > 0:
            plus_dm[i] = hd
        if ld > hd and ld > 0:
            minus_dm[i] = ld

    def wilder_smooth(arr: np.ndarray, p: int) -> np.ndarray:
        res = np.zeros(len(arr))
        if len(arr) < p:
            return res
        res[p - 1] = np.mean(arr[:p])
        alpha = 1.0 / p
        for i in range(p, len(arr)):
            res[i] = arr[i] * alpha + res[i - 1] * (1 - alpha)
        return res

    atr = wilder_smooth(tr, period)
    plus_di_raw = wilder_smooth(plus_dm, period)
    minus_di_raw = wilder_smooth(minus_dm, period)

    plus_di = np.zeros(len(h))
    minus_di = np.zeros(len(h))
    for i in range(len(h)):
        if atr[i] > 0:
            plus_di[i] = 100 * plus_di_raw[i] / atr[i]
            minus_di[i] = 100 * minus_di_raw[i] / atr[i]

    dx = np.zeros(len(h))
    for i in range(len(h)):
        s = plus_di[i] + minus_di[i]
        if s > 0:
            dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / s

    adx = wilder_smooth(dx, smoothing)

    return (
        [Decimal(str(v)) for v in adx],
        [Decimal(str(v)) for v in plus_di],
        [Decimal(str(v)) for v in minus_di],
    )