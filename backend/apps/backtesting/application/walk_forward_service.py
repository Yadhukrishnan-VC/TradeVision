"""Batch WALKFORWARD-VALIDATION-1 — rolling walk-forward validation.

Pure orchestrator: it introduces **no new persistence model** and reuses the
*unmodified* single-run engine end-to-end. For each sliding date window it
creates a dedicated, isolated ``BacktestRun`` (its own funded account, so
``run_stats`` never sees another window's records), executes it through the
real ``BacktestRunnerService``, then reuses ``BacktestStatsService.run_stats``
for the per-window in-sample/out-of-sample metrics.

The walk-forward summary is the cross-window distribution (min / max / median /
count_positive) of the out-of-sample expectancy, Sharpe ratio and win rate,
computed only over windows whose out-of-sample half held at least
``MIN_TRADES_FOR_DISTRIBUTION`` trades.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Sequence

from apps.accounts.infrastructure.models import Account
from apps.backtesting.models import BacktestRun
from apps.backtesting.repository import BacktestRunRepository
from apps.backtesting.services import BacktestRunnerService, BacktestStatsService
from apps.portfolio.application.capital_service import CapitalService
from core.services import BaseService

#: A window's out-of-sample half must have at least this many trades before its
#: metrics enter the cross-window distribution.
MIN_TRADES_FOR_DISTRIBUTION = 2


def generate_windows(
    range_start: datetime,
    range_end: datetime,
    window_size: timedelta,
    step_size: timedelta,
) -> list[tuple[datetime, datetime]]:
    """Sliding ``window_size``-long windows with strictly increasing starts.

    Every window is full-size and must fit completely inside
    ``[range_start, range_end]``. A zero/negative ``step_size`` is a degenerate
    spec and falls back to a full ``window_size`` step to stay bounded.
    """
    if step_size <= timedelta(0):
        step_size = window_size
    windows: list[tuple[datetime, datetime]] = []
    cursor = range_start
    while cursor + window_size <= range_end:
        windows.append((cursor, cursor + window_size))
        cursor = cursor + step_size
    return windows


def _median(values: Sequence[Decimal]) -> Decimal:
    ordered = sorted(values)
    n = len(ordered)
    midpoint = n // 2
    if n % 2 == 1:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def calculate_distribution(values: Sequence[Decimal]) -> dict[str, Any]:
    """min / max / mean / median / count_positive over a sequence of Decimals.

    All numeric values are emitted as strings (Decimal is not JSON
    serialisable); ``count_positive`` is the number of values strictly above
    zero. An empty input yields all-None extrema so downstream callers always
    get the same response shape.
    """
    if not values:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "count_positive": 0,
        }
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min": str(ordered[0]),
        "max": str(ordered[-1]),
        "mean": str(sum(ordered) / len(ordered)),
        "median": str(_median(ordered)),
        "count_positive": sum(1 for v in ordered if v > Decimal("0")),
    }


class WalkForwardService(BaseService):
    """Runs the single-run engine once per sliding window and aggregates OOS."""

    def __init__(
        self,
        *,
        runner: BacktestRunnerService | None = None,
        stats: BacktestStatsService | None = None,
        run_repo: BacktestRunRepository | None = None,
        capital: CapitalService | None = None,
    ) -> None:
        super().__init__()
        self._runner = runner or BacktestRunnerService()
        self._stats = stats or BacktestStatsService()
        self._runs = run_repo or BacktestRunRepository()
        self._capital = capital or CapitalService()

    def execute(
        self,
        *,
        owner: Any,
        symbol: str,
        timeframe: str,
        range_start: datetime,
        range_end: datetime,
        window_size_days: int,
        step_size_days: int,
        in_sample_ratio: Decimal = Decimal("0.70"),
        initial_capital: Decimal = Decimal("1000000"),
        commission_rate: Decimal = Decimal("0"),
        slippage_bps: Decimal = Decimal("0"),
    ) -> dict[str, Any]:
        """Validate ``symbol`` walk-forward over the requested range.

        Returns per-window stats (identical to a direct ``run_stats`` call for
        that window) plus the OOS distribution described at module level. The
        ``run_stats`` partition for each window uses the same static
        ``in_sample_ratio`` split the single-run API exposes.
        """
        windows = generate_windows(
            range_start,
            range_end,
            timedelta(days=window_size_days),
            timedelta(days=step_size_days),
        )

        per_window: list[dict[str, Any]] = []
        for index, (win_start, win_end) in enumerate(windows):
            account = Account.objects.create(
                name=f"WalkForward {symbol} window-{index}",
                owner=owner,
                is_default=False,
            )
            self._capital.deposit(account.id, initial_capital)
            run = BacktestRun(
                symbol=symbol,
                timeframe=timeframe,
                range_start=win_start,
                range_end=win_end,
                account=account,
                status="PENDING",
                commission_rate=commission_rate,
                slippage_bps=slippage_bps,
                in_sample_ratio=in_sample_ratio,
            )
            self._runs.create(run)

            run_result = self._runner.run(run.id)
            stats = self._stats.run_stats(run)
            oos = stats["out_of_sample"]
            per_window.append(
                {
                    "window_index": index,
                    "range_start": win_start.isoformat(),
                    "range_end": win_end.isoformat(),
                    "run_id": str(run.id),
                    "account_id": str(account.id),
                    "status": run_result.get("status", ""),
                    "in_sample_trade_count": stats["in_sample"]["trade_count"],
                    "out_of_sample_trade_count": oos["trade_count"],
                    "in_sample_expectancy": stats["in_sample"]["expectancy"],
                    "out_of_sample_expectancy": oos["expectancy"],
                    "out_of_sample_sharpe_ratio": oos["sharpe_ratio"],
                    "out_of_sample_win_rate": oos["win_rate"],
                }
            )

        included = [
            window
            for window in per_window
            if window["out_of_sample_trade_count"] >= MIN_TRADES_FOR_DISTRIBUTION
        ]
        excluded = len(per_window) - len(included)

        sharpe_values = [
            Decimal(window["out_of_sample_sharpe_ratio"])
            for window in included
            if window["out_of_sample_sharpe_ratio"] is not None
        ]

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "range_start": range_start.isoformat(),
            "range_end": range_end.isoformat(),
            "window_size_days": window_size_days,
            "step_size_days": step_size_days,
            "in_sample_ratio": str(in_sample_ratio),
            "total_windows": len(per_window),
            "included_window_count": len(included),
            "excluded_window_count": excluded,
            "windows": per_window,
            "distribution": {
                "out_of_sample_expectancy": calculate_distribution(
                    [Decimal(w["out_of_sample_expectancy"]) for w in included]
                ),
                "out_of_sample_sharpe_ratio": calculate_distribution(sharpe_values),
                "out_of_sample_win_rate": calculate_distribution(
                    [Decimal(w["out_of_sample_win_rate"]) for w in included]
                ),
            },
        }