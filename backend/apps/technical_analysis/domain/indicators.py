"""Deterministic indicator math for the REST polling bridge (Batch M5).

This module is deliberately pure: no Django imports, no I/O, and every
function is a plain mathematical function of an already-ordered list of
bar-shaped objects (each exposing ``high``, ``low``, ``close`` and
``volume``). Nothing in this module looks at the wall clock, a calendar, or
any persistence layer.

Ownership split (approved M5 package):

* **Technical_analysis · this module** — calendar-agnostic arithmetic. The
  caller decides *which* candles are in scope and their order.
* **market_data · candle_ta_bridge** — orchestration: slices candle history
  (via ``CandleRepository.find_latest``) and the VWAP session window (via
  ``SessionFactsService`` derived session boundary) before calling here.

Warm-up policy — every function that needs a fixed window returns ``None``
(never ``0``, never a fabricated value) when given fewer than its minimum
number of candles:

============= ================== ===========================================
Indicator     Minimum candles     Behavior below the minimum
============= ==================  ===========================================
VWAP          1                   ``None`` when the session slice is empty
                                  or carries zero total volume
EMA20         20                  ``None`` (SMA seed needs ``period`` closes)
ATR14         15                  ``None`` (14 true ranges + 1 prior close)
Bollinger U.  20                  ``None`` (full sampling window required)
============= ==================  ===========================================

These are the pure-function minima from the approved warm-up table. The
stability gate for EMA20 (Decision C: only treat the value as decision-grade
once 60 candles are available) is enforced by the *caller*
(``candle_ta_bridge``), not here.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

Bar = Any
"""A bar-shaped object exposing ``low``, ``close`` and ``volume``."""


def compute_vwap(candles: Sequence[Bar]) -> Decimal | None:
    """Session VWAP over *candles*: ``sum(tp * volume) / sum(volume)``.

    ``tp = (high + low + close) / 3``. Session/reset semantics are the
    caller's responsibility (pass exactly the session slice). Candles with
    zero or non-positive volume contribute nothing. The function is not order
    sensitive, but the caller is expected to pass chronological candles so
    the result is attributable to a clean, contiguous session window.

    Returns ``None`` when the series is empty or carries zero total volume —
    there is no VWAP to report, and ``None`` (not ``0``) is the contract.
    """
    total_amount = Decimal("0")
    total_volume = 0
    for candle in candles:
        volume = int(candle.volume)
        if volume <= 0:
            continue
        typical = (
            Decimal(candle.high) + Decimal(candle.low) + Decimal(candle.close)
        ) / Decimal("3")
        total_amount += typical * Decimal(volume)
        total_volume += volume

    if total_volume <= 0:
        return None
    return total_amount / Decimal(total_volume)


def compute_ema(candles: Sequence[Bar], period: int = 20) -> Decimal | None:
    """Exponential moving average seeded by the SMA of the first *period* closes.

    ``ema_t = close_t * k + ema_{t-1} * (1 - k)`` with ``k = 2 / (period + 1)``.

    Returns ``None`` when fewer than *period* candles are supplied (the seed
    needs a full SMA window). The result is the EMA at the *last* candle.
    """
    if len(candles) < period:
        return None
    k = Decimal("2") / Decimal(period + 1)
    closes = [Decimal(c.close) for c in candles]
    ema = sum(closes[:period]) / Decimal(period)
    for close in closes[period:]:
        ema = close * k + ema * (Decimal("1") - k)
    return ema


def compute_atr(candles: Sequence[Bar], period: int = 14) -> Decimal | None:
    """Wilder average true range.

    ``TR_t = max(high - low, |high - close_{t-1}|, |low - close_{t-1}|)``.
    The first ATR is the SMA of the first *period* true ranges followed by
    Wilder smoothing: ``ATR_t = (ATR_{t-1} * (period-1) + TR_t) / period``.

    Returns ``None`` unless at least ``period + 1`` candles exist (``period``
    true ranges need a preceding close). The result is the ATR at the *last*
    candle.
    """
    if len(candles) < period + 1:
        return None

    true_ranges: list[Decimal] = []
    for idx in range(1, len(candles)):
        high = Decimal(candles[idx].high)
        low = Decimal(candles[idx].low)
        prev_close = Decimal(candles[idx - 1].close)
        true_ranges.append(
            max(high - low, abs(high - prev_close), abs(low - prev_close))
        )

    atr = sum(true_ranges[:period]) / Decimal(period)
    for tr in true_ranges[period:]:
        atr = (atr * Decimal(period - 1) + tr) / Decimal(period)
    return atr


def compute_bollinger_upper(
    candles: Sequence[Bar],
    period: int = 20,
    num_std: Decimal = Decimal("2"),
    sample: bool = True,
) -> Decimal | None:
    """Bollinger upper band: ``SMA(close, period) + num_std * stddev``.

    Standard-deviation convention (approved Decision B): the default uses
    *sample* standard deviation (Bessel's correction, N-1), matching the
    TradingView ``ta.bb()`` default that prior Pine-supplied values in this
    system were written against. ``sample=False`` switches to the population
    standard deviation (N).

    Returns ``None`` when fewer than *period* closes are available.
    """
    if len(candles) < period:
        return None
    closes = [Decimal(c.close) for c in candles[-period:]]
    mean = sum(closes) / Decimal(period)
    denominator = Decimal(period - 1) if sample else Decimal(period)
    variance = sum((close - mean) ** 2 for close in closes) / denominator
    stddev = variance.sqrt()
    return mean + Decimal(num_std) * stddev