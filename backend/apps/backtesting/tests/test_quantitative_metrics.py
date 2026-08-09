from decimal import Decimal

import pytest

from apps.backtesting.domain.metrics import (
    calculate_benchmark_return,
    calculate_expectancy,
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
)


def test_calculate_expectancy():
    # 60% win rate, avg win 1000, avg loss 500, avg cost 50
    # E = 0.6 * 1000 - 0.4 * 500 - 50 = 600 - 200 - 50 = 350
    exp = calculate_expectancy(
        win_rate=Decimal("0.60"),
        avg_win=Decimal("1000.00"),
        avg_loss=Decimal("500.00"),
        avg_cost=Decimal("50.00"),
    )
    assert exp == Decimal("350.00")


def test_calculate_profit_factor():
    pf = calculate_profit_factor(
        gross_profit=Decimal("15000.00"),
        gross_loss=Decimal("5000.00"),
        total_costs=Decimal("1000.00"),
    )
    # 15000 / 6000 = 2.5
    assert pf == Decimal("2.5")


def test_calculate_max_drawdown():
    equity_curve = [
        Decimal("100000.00"),
        Decimal("110000.00"),  # Peak
        Decimal("99000.00"),   # DD: 11000 (10%)
        Decimal("105000.00"),
        Decimal("120000.00"),  # New peak
        Decimal("108000.00"),  # DD: 12000 (10%)
    ]
    max_dd_pct, max_dd_amount = calculate_max_drawdown(equity_curve)
    assert max_dd_amount == Decimal("12000.00")
    assert max_dd_pct == Decimal("10.00")


def test_calculate_sharpe_and_sortino():
    daily_returns = [
        Decimal("0.01"),
        Decimal("0.02"),
        Decimal("-0.005"),
        Decimal("0.015"),
        Decimal("0.01"),
    ]
    sharpe = calculate_sharpe_ratio(daily_returns)
    sortino = calculate_sortino_ratio(daily_returns)
    assert sharpe is not None and sharpe > Decimal("0")
    assert sortino is not None and sortino > Decimal("0")


def test_calculate_benchmark_return():
    ret = calculate_benchmark_return(Decimal("100.00"), Decimal("115.00"))
    assert ret == Decimal("15.00")
