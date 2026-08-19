"""Shuffled-baseline significance module — known-answer tests.

The module is tested against ground-truth fixtures, NOT against TradeVision's
real rules:

- a strategy that is literally random (symmetric, zero-mean trade P&L) must
  report ``NOT_SIGNIFICANT``,
- a sequence with an injected, obvious positive edge must report
  ``SIGNIFICANT``,
- samples too small to support any claim must report no verdict
  (``INSUFFICIENT_TRADES``), never a false positive.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.backtesting.domain.significance import (
    MIN_TRADES_FOR_TEST,
    shuffled_baseline_significance,
)


def test_random_strategy_reports_not_significant() -> None:
    trade_pnls = [1.0, -1.0] * 8
    result = shuffled_baseline_significance(trade_pnls, seed=42)
    assert result.n_trades == 16
    assert result.observed_mean == pytest.approx(0.0)
    assert result.verdict == "NOT_SIGNIFICANT"
    assert result.significant is False
    assert result.p_value is not None and result.p_value > result.alpha


def test_injected_positive_edge_reports_significant() -> None:
    trade_pnls = [1.0] * 12
    result = shuffled_baseline_significance(trade_pnls, seed=42)
    assert result.observed_mean == pytest.approx(1.0)
    assert result.verdict == "SIGNIFICANT"
    assert result.significant is True
    assert result.p_value is not None
    assert result.p_value <= result.alpha
    assert result.p_value <= 0.01


def test_below_min_trades_reports_no_verdict() -> None:
    trade_pnls = [1.0, -1.0, 1.0, -1.0, 1.0]
    result = shuffled_baseline_significance(trade_pnls, seed=7)
    assert result.n_trades == 5
    assert result.verdict is None
    assert result.significant is None
    assert result.p_value is None
    assert result.reason == "INSUFFICIENT_TRADES"


def test_empty_sequence_reports_no_verdict() -> None:
    result = shuffled_baseline_significance([], seed=7)
    assert result.verdict is None
    assert result.significant is None
    assert result.reason == "INSUFFICIENT_TRADES"


def test_min_trades_threshold_is_honored() -> None:
    trade_pnls = [1.0] * (MIN_TRADES_FOR_TEST - 1)
    result = shuffled_baseline_significance(trade_pnls, seed=7)
    assert result.verdict is None

    trade_pnls = [1.0] * MIN_TRADES_FOR_TEST
    result = shuffled_baseline_significance(trade_pnls, seed=7)
    assert result.verdict == "SIGNIFICANT"


def test_deterministic_with_seed() -> None:
    trade_pnls = [1.0, -2.0, 3.0, -1.0, 2.0, -0.5, 1.5, -1.0, 2.5, -2.0, 1.0, -0.5]
    first = shuffled_baseline_significance(trade_pnls, seed=1234)
    second = shuffled_baseline_significance(trade_pnls, seed=1234)
    assert first.p_value == second.p_value
    assert first.baseline_mean == second.baseline_mean
    assert first.z_score == second.z_score


def test_accepts_decimal_input() -> None:
    trade_pnls = [Decimal("1.00")] * 12
    result = shuffled_baseline_significance(trade_pnls, seed=5)
    assert result.verdict == "SIGNIFICANT"
    assert result.observed_mean == pytest.approx(1.0)


def test_rejects_invalid_arguments() -> None:
    trade_pnls = [1.0] * 12
    with pytest.raises(ValueError):
        shuffled_baseline_significance(trade_pnls, n_shuffles=0)
    with pytest.raises(ValueError):
        shuffled_baseline_significance(trade_pnls, alpha=0.0)
    with pytest.raises(ValueError):
        shuffled_baseline_significance(trade_pnls, alpha=1.0)


def test_baseline_preserves_trade_frequency() -> None:
    trade_pnls = [1.0, -1.0] * 8
    result = shuffled_baseline_significance(trade_pnls, seed=9)
    assert result.n_trades == 16
    assert result.baseline_mean == pytest.approx(0.0, abs=0.2)
    assert result.baseline_std > 0
