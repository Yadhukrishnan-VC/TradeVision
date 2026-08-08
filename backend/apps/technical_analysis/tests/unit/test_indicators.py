"""Unit tests for the pure indicator math (Batch M5).

The module is calendar-agnostic: these tests exercise the arithmetic with a
local bar-shaped dataclass, proving known-input / known-output behaviour,
warm-up boundaries, zero-volume handling, ordering sensitivity, and
deterministic re-computation in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest

from apps.technical_analysis.domain.indicators import (
    compute_atr,
    compute_bollinger_upper,
    compute_ema,
    compute_vwap,
)


@dataclass
class Bar:
    high: str
    low: str
    close: str
    volume: int


def _bars(*closes: tuple[str, str, str, int]) -> list[Bar]:
    """Build a bar list from ``(high, low, close, volume)`` tuples."""
    return [Bar(high=h, low=l, close=c, volume=v) for h, l, c, v in closes]


# ---------------------------------------------------------------------------
# VWAP
# ---------------------------------------------------------------------------


class TestComputeVwap:
    def test_three_candle_known_value(self) -> None:
        bars = _bars(
            ("100", "100", "100", 100),
            ("101", "101", "101", 200),
            ("102", "102", "102", 500),
        )
        # tp = (h+l+c)/3, weighted by volume:
        #   (100 * 100) + (101 * 200) + (102 * 500) = 81200 / 800 = 101.5
        assert compute_vwap(bars) == Decimal("101.500")
        # repeatability
        assert compute_vwap(bars) == compute_vwap(bars)

    def test_known_manual_expectation(self) -> None:
        # tp = 100.5 (vol 100), tp = 100.5 (vol 200), tp = 101.5 (vol 500)
        # => (100.5*100 + 100.5*200 + 101.5*500) / 800 = 101.125
        bars = _bars(
            ("100", "100", "101.5", 100),
            ("100", "100", "101.5", 200),
            ("101", "100", "103.5", 500),
        )
        assert compute_vwap(bars) == Decimal("101.125")

    def test_empty_returns_none(self) -> None:
        assert compute_vwap([]) is None

    def test_zero_volume_returns_none(self) -> None:
        bars = _bars(("100", "100", "100", 0), ("101", "101", "101", 0))
        assert compute_vwap(bars) is None

    def test_zero_volume_candle_is_skipped_not_error(self) -> None:
        bars = _bars(("100", "100", "100", 0), ("101", "101", "101", 500))
        assert compute_vwap(bars) == Decimal("101")

    def test_order_independent(self) -> None:
        bars = _bars(
            ("100", "100", "100", 100),
            ("101", "101", "101", 200),
            ("102", "102", "102", 500),
        )
        assert compute_vwap(list(reversed(bars))) == compute_vwap(bars)


# ---------------------------------------------------------------------------
# EMA20
# ---------------------------------------------------------------------------


class TestComputeEma:
    def test_constant_series_converges_to_value(self) -> None:
        bars = _bars(*[("100", "100", "100", 1000)] * 60)
        assert compute_ema(bars) == Decimal("100")

    def test_known_value_range_1_to_30(self) -> None:
        bars = _bars(*[("c", "c", str(i), 1000) for i in range(1, 31)])
        assert compute_ema(bars) == Decimal("20.50000000000000000000000000")

    def test_insufficient_history_returns_none(self) -> None:
        bars = _bars(*[("100", "100", "100", 1000)] * 19)
        assert compute_ema(bars, period=20) is None

    def test_exactly_period_candles_returns_seed(self) -> None:
        bars = _bars(*[("100", "100", str(i), 1000) for i in range(1, 21)])
        # SMA of first 20 closes = (1..20 mean) = 10.5
        assert compute_ema(bars, period=20) == Decimal("10.5")

    def test_deterministic_repeat(self) -> None:
        bars = _bars(*[("100", "100", str(i % 5), 1000) for i in range(1, 40)])
        assert compute_ema(bars) == compute_ema(bars)

    def test_order_sensitive(self) -> None:
        ascending = _bars(*[("c", "c", str(i), 1000) for i in range(1, 31)])
        descending = list(reversed(ascending))
        assert compute_ema(ascending) != compute_ema(descending)


# ---------------------------------------------------------------------------
# ATR14
# ---------------------------------------------------------------------------


class TestComputeAtr:
    def test_constant_range_known_value(self) -> None:
        # TR = max(h-l=2, |h-prev|, |l-prev|); with h=101, l=99, close=100
        # and a flat prior close the TR is constant 2 => ATR = 2.
        bars = _bars(*[("101", "99", "100", 1000)] * 16)
        assert compute_atr(bars) == Decimal("2")

    def test_wilder_smoothing_step(self) -> None:
        # First TR = 2 for 14 candles then a 4-unit jump on candle 16.
        bars = _bars(*[("101", "99", "100", 1000)] * 15)
        bars.append(Bar(high="104", low="100", close="102", volume=1000))
        first_atr = sum([Decimal("2")] * 14) / Decimal("14")
        # ATR_15 = (first_atr * 13 + 4) / 14
        expected = (first_atr * 13 + Decimal("4")) / Decimal("14")
        assert compute_atr(bars) == expected

    def test_insufficient_history_returns_none(self) -> None:
        bars = _bars(*[("101", "99", "100", 1000)] * 14)
        assert compute_atr(bars, period=14) is None

    def test_exactly_period_plus_one_candles(self) -> None:
        bars = _bars(*[("101", "99", "100", 1000)] * 15)
        assert compute_atr(bars, period=14) == Decimal("2")

    def test_deterministic_repeat(self) -> None:
        bars = _bars(*[("10%d" % (i % 3), "98", "100", 1000) for i in range(20)])
        assert compute_atr(bars) == compute_atr(bars)


# ---------------------------------------------------------------------------
# Bollinger Upper Band
# ---------------------------------------------------------------------------


class TestComputeBollingerUpper:
    def test_constant_series_upper_equals_sma(self) -> None:
        # stddev 0 => upper band == SMA == 100
        bars = _bars(*[("100", "100", "100", 1000)] * 20)
        assert compute_bollinger_upper(bars) == Decimal("100")

    def test_known_two_point_sample_stddev(self) -> None:
        # closes alternate 100 / 101: mean 100.5, sample variance 5/19
        # => upper = 100.5 + 2 * sqrt(5/19) = 101.52597835...
        bars = _bars(*[("c", "c", "100" if i % 2 == 0 else "101", 1000) for i in range(20)])
        assert compute_bollinger_upper(bars) == Decimal("101.5259783520851540954566751")

    def test_sample_vs_population_differ(self) -> None:
        bars = _bars(*[("c", "c", str(100 + (i % 5)), 1000) for i in range(20)])
        sample = compute_bollinger_upper(bars, sample=True)
        population = compute_bollinger_upper(bars, sample=False)
        assert sample is not None and population is not None
        # With N-1 < N the sample variance is larger, so the upper band is higher.
        assert sample > population

    def test_insufficient_history_returns_none(self) -> None:
        bars = _bars(*[("100", "100", "100", 1000)] * 19)
        assert compute_bollinger_upper(bars) is None

    def test_deterministic_repeat(self) -> None:
        bars = _bars(*[("100", "100", str(100 + (i % 3)), 1000) for i in range(25)])
        assert compute_bollinger_upper(bars) == compute_bollinger_upper(bars)


# ---------------------------------------------------------------------------
# Cross-cutting: no fabricated zeroes under insufficient data
# ---------------------------------------------------------------------------


class TestWarmupFailSafe:
    def test_all_indicators_none_with_two_candles(self) -> None:
        bars = _bars(("101", "99", "100", 1000), ("102", "100", "101", 1000))
        assert compute_vwap(bars) is not None  # vwap is defined for one+ candles
        assert compute_ema(bars, period=20) is None
        assert compute_atr(bars, period=14) is None
        assert compute_bollinger_upper(bars) is None

    def test_never_returns_zero_as_substitute(self) -> None:
        bars = _bars(*[("100", "100", "100", 1000)] * 5)
        for value in (
            compute_ema(bars, period=20),
            compute_atr(bars, period=14),
            compute_bollinger_upper(bars),
        ):
            assert value is None

    @pytest.mark.parametrize(
        "builder",
        [
            lambda: compute_vwap([]),
            lambda: compute_ema([], period=20),
            lambda: compute_atr([], period=14),
            lambda: compute_bollinger_upper([]),
        ],
        ids=["vwap", "ema", "atr", "bb"],
    )
    def test_empty_series_is_none_not_zero(self, builder) -> None:
        assert builder() is None