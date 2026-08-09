"""Pure mathematical functions for strategy performance & statistical edge metrics (Batch M3.8).

Deliberately pure: no Django models, no DB connections, no side effects. All inputs
and outputs use Decimal for deterministic financial precision.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Sequence


def calculate_expectancy(
    win_rate: Decimal,
    avg_win: Decimal,
    avg_loss: Decimal,
    avg_cost: Decimal = Decimal("0"),
) -> Decimal:
    """Cost-adjusted expectancy per trade: E = (WR * AvgWin) - ((1 - WR) * AvgLoss) - AvgCost.

    Returns currency amount expected per trade after costs.
    """
    loss_rate = Decimal("1") - win_rate
    return (win_rate * avg_win) - (loss_rate * avg_loss) - avg_cost


def calculate_profit_factor(
    gross_profit: Decimal,
    gross_loss: Decimal,
    total_costs: Decimal = Decimal("0"),
) -> Decimal | None:
    """Profit factor: Gross Profit / (Gross Loss + Total Costs).

    Returns None when there are no losses or costs and zero profit. Returns Decimal('inf')
    or a bounded high value when profit exists with zero denominator.
    """
    denominator = gross_loss + total_costs
    if denominator == Decimal("0"):
        if gross_profit > Decimal("0"):
            return Decimal("999.99")
        return None
    return gross_profit / denominator


def calculate_max_drawdown(
    equity_series: Sequence[Decimal],
) -> tuple[Decimal, Decimal]:
    """Calculate maximum drawdown (percentage and absolute currency depth).

    Returns tuple (max_drawdown_pct, max_drawdown_amount).
    """
    if not equity_series or len(equity_series) < 2:
        return Decimal("0"), Decimal("0")

    peak = equity_series[0]
    max_dd_amount = Decimal("0")
    max_dd_pct = Decimal("0")

    for value in equity_series:
        if value > peak:
            peak = value
        else:
            dd_amount = peak - value
            if dd_amount > max_dd_amount:
                max_dd_amount = dd_amount
            if peak > Decimal("0"):
                dd_pct = (dd_amount / peak) * Decimal("100")
                if dd_pct > max_dd_pct:
                    max_dd_pct = dd_pct

    return max_dd_pct, max_dd_amount


def calculate_sharpe_ratio(
    daily_returns: Sequence[Decimal],
    risk_free_rate: Decimal = Decimal("0"),
) -> Decimal | None:
    """Annualized Sharpe Ratio: (Mean Return - Risk Free) / Std Dev * sqrt(252).

    Returns None when fewer than 2 return samples exist or std dev is zero.
    """
    if not daily_returns or len(daily_returns) < 2:
        return None

    returns_float = [float(r) for r in daily_returns]
    rf_float = float(risk_free_rate)
    n = len(returns_float)

    mean_ret = sum(returns_float) / n
    variance = sum((r - mean_ret) ** 2 for r in returns_float) / (n - 1)
    std_dev = math.sqrt(variance)

    if std_dev <= 0:
        return None

    annualized_sharpe = ((mean_ret - rf_float) / std_dev) * math.sqrt(252)
    return Decimal(str(round(annualized_sharpe, 4)))


def calculate_sortino_ratio(
    daily_returns: Sequence[Decimal],
    risk_free_rate: Decimal = Decimal("0"),
) -> Decimal | None:
    """Annualized Sortino Ratio: (Mean Return - Risk Free) / Downside Std Dev * sqrt(252).

    Only negative returns contribute to downside risk. Returns None when no downside risk exists.
    """
    if not daily_returns or len(daily_returns) < 2:
        return None

    returns_float = [float(r) for r in daily_returns]
    rf_float = float(risk_free_rate)
    n = len(returns_float)

    mean_ret = sum(returns_float) / n
    downside_returns = [min(0.0, r - rf_float) for r in returns_float]
    downside_variance = sum(dr**2 for dr in downside_returns) / (n - 1)
    downside_std = math.sqrt(downside_variance)

    if downside_std <= 0:
        return None

    annualized_sortino = ((mean_ret - rf_float) / downside_std) * math.sqrt(252)
    return Decimal(str(round(annualized_sortino, 4)))


def calculate_benchmark_return(
    start_price: Decimal,
    end_price: Decimal,
) -> Decimal | None:
    """Buy-and-Hold benchmark return percentage: (end_price - start_price) / start_price * 100."""
    if start_price is None or start_price <= Decimal("0") or end_price is None:
        return None
    return ((end_price - start_price) / start_price) * Decimal("100")
