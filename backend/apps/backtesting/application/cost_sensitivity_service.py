"""Batch COST-SENSITIVITY-1 — per-rule commission/slippage cost-breakeven analysis.

This batch is a pure orchestrator, exactly like WALKFORWARD-VALIDATION-1: it
introduces **no new persistence model** and reuses the *unmodified* single-run
engine end-to-end. For each point in a caller-supplied
``(commission_rate, slippage_bps)`` grid it creates one dedicated, isolated
``BacktestRun`` (its own funded account, so no point's fills or costs can
contaminate another), executes the real ``BacktestRunnerService``, then reads
per-rule expectancy from ``BacktestStatsService.run_stats()["by_rule"]``
(RULE-ATTRIBUTION-1). After the full sweep it derives, for every rule that
traded in at least one point, the cost level at which that rule's expectancy
crosses zero — its cost breakeven.

A single scalar `cost level` drives the breakeven math. ``run_stats`` applies a
per-trade cost rate of ``commission_rate + slippage_bps / 10000`` (commission
fee plus slippage impact), so that combined rate is the natural monotone axis
along which a rule's expectancy can be interpolated. Breakevens are reported
twice: once as the equivalent pure-commission rate (zero slippage) and once as
the equivalent pure slippage in bps (zero commission) — the same total per-trade
cost budget expressed in the two units the engine consumes.

Trading correctness: this batch adds zero temporal logic. Every grid-point run
goes through the same ``bind_simulated_time``-wrapped, next-bar-fill,
gap-through-stop-loss engine as every existing backtest; the only novelty is
running it N times with different cost scalars and comparing ``by_rule``
outputs. ``metrics.py`` and ``services.py`` are called, never modified.
"""

from __future__ import annotations

import itertools
from datetime import datetime
from decimal import Decimal
from typing import Any

from apps.accounts.infrastructure.models import Account
from apps.backtesting.models import BacktestRun
from apps.backtesting.repository import BacktestRunRepository
from apps.backtesting.services import BacktestRunnerService, BacktestStatsService
from apps.portfolio.application.capital_service import CapitalService
from core.services import BaseService

#: Upper bound on the number of grid points one sweep may run. Kept small so a
#: sweep stays a synchronous, bounded HTTP operation (mirrors the bounded
#: window validation in WALKFORWARD-VALIDATION-1).
MAX_GRID_POINTS = 50

#: Numeric denominators used to translate between the two cost units the
#: engine consumes (commission is a rate, slippage is in basis points).
_SLIPPAGE_BPS_PER_UNIT = Decimal(10000)

CLASSIFICATION_BREAKEVEN_FOUND = "BREAKEVEN_FOUND"
CLASSIFICATION_NEVER_PROFITABLE = "NEVER_PROFITABLE"
CLASSIFICATION_SURVIVES_FULL_RANGE = "SURVIVES_FULL_RANGE"


def _decimal_range(start: Decimal, stop: Decimal, step: Decimal) -> list[Decimal]:
    """Inclusive ``[start, stop]`` Decimal progression by ``step``."""
    values: list[Decimal] = []
    value = start
    while value <= stop:
        values.append(value)
        value += step
    return values


def generate_cost_grid(
    commission_range: tuple[Decimal, Decimal],
    commission_step: Decimal,
    slippage_range: tuple[Decimal, Decimal],
    slippage_step: Decimal,
) -> list[tuple[Decimal, Decimal]]:
    """Grid of ``(commission_rate, slippage_bps)`` sweep points.

    Pure function — no ORM, no Django imports. The grid is the cartesian
    product of the commission progression (outer axis) and the slippage
    progression (inner axis), both ascending, so the ordering is fully
    deterministic for a given input. Invalid step/range inputs raise
    ``ValueError`` rather than silently producing an empty or infinite grid.
    """
    commission_start, commission_end = commission_range
    slippage_start, slippage_end = slippage_range
    if commission_step <= Decimal(0):
        raise ValueError(f"commission_step must be positive, got {commission_step}")
    if slippage_step <= Decimal(0):
        raise ValueError(f"slippage_step must be positive, got {slippage_step}")
    if commission_end < commission_start:
        raise ValueError(
            "commission_end must be >= commission_start, "
            f"got {commission_start}..{commission_end}"
        )
    if slippage_end < slippage_start:
        raise ValueError(
            "slippage_end must be >= slippage_start, "
            f"got {slippage_start}..{slippage_end}"
        )

    commissions = _decimal_range(commission_start, commission_end, commission_step)
    slippages = _decimal_range(slippage_start, slippage_end, slippage_step)
    return [(commission, slippage) for commission in commissions for slippage in slippages]


def cost_level(commission_rate: Decimal, slippage_bps: Decimal) -> Decimal:
    """Combined per-trade cost rate a grid point imposes on the engine.

    ``run_stats`` totals per-order cost as
    ``qty * fill * commission_rate + qty * fill * (slippage_bps / 10000)``, so
    the combined rate ``commission_rate + slippage_bps / 10000`` is the single
    scalar that determines expectancy at a grid point.
    """
    return commission_rate + slippage_bps / _SLIPPAGE_BPS_PER_UNIT


def find_breakeven(sweep_results: list[dict[str, Any]]) -> Decimal | None:
    """Cost level at which a rule's expectancy first crosses zero.

    Args:
        sweep_results: list of ``{"cost_level": Decimal, "expectancy": Decimal}``
            observations for one rule, one per successful grid point (order
            independent — the sequence is sorted by ``cost_level`` here).

    Returns:
        The interpolated exception-crossing cost level, ``None`` when the
        rule never crosses zero at any tested level (either it had no edge to
        lose, or its edge survives the entire tested range — the caller must
        distinguish those two with the surrounding classification logic).
    """
    if not sweep_results:
        return None
    ordered = sorted(sweep_results, key=lambda row: row["cost_level"])
    for row in ordered:
        if row["expectancy"] == 0:
            return row["cost_level"]
    for current, following in itertools.pairwise(ordered):
        e1 = current["expectancy"]
        e2 = following["expectancy"]
        if (e1 < 0 < e2) or (e2 < 0 < e1):
            c1 = current["cost_level"]
            c2 = following["cost_level"]
            return c1 + ((c2 - c1) * (-e1)) / (e2 - e1)
    return None


class CostSensitivityService(BaseService):
    """Runs the single-run engine once per cost grid point and derives breakevens."""

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
        range_start: datetime,
        range_end: datetime,
        symbol: str,
        commission_range: tuple[Decimal, Decimal],
        commission_step: Decimal,
        slippage_range: tuple[Decimal, Decimal],
        slippage_step: Decimal,
        timeframe: str = "",
        initial_capital: Decimal = Decimal(1000000),
    ) -> dict[str, Any]:
        """Sweep a cost grid over a fixed historical window and derive breakevens.

        Returns a report keyed by ``rule_id`` with the expectancy at the lowest
        and highest tested cost levels, the interpolated breakeven (when found),
        and a classification (``BREAKEVEN_FOUND`` / ``NEVER_PROFITABLE`` /
        ``SURVIVES_FULL_RANGE``). The full per-grid-point series for each rule
        is included so noisy, non-monotonic curves can be inspected rather than
        trusted to a single interpolated number.
        """
        grid = generate_cost_grid(
            commission_range, commission_step, slippage_range, slippage_step
        )
        if len(grid) > MAX_GRID_POINTS:
            raise ValueError(
                f"cost grid exceeds MAX_GRID_POINTS={MAX_GRID_POINTS}: got {len(grid)}"
            )

        collected: dict[str, list[dict[str, Any]]] = {}
        completed = 0
        for index, (commission_rate, slippage_bps) in enumerate(grid):
            try:
                by_rule = self._run_point(
                    owner=owner,
                    symbol=symbol,
                    timeframe=timeframe,
                    range_start=range_start,
                    range_end=range_end,
                    commission_rate=commission_rate,
                    slippage_bps=slippage_bps,
                    initial_capital=initial_capital,
                    point_index=index,
                )
            except Exception:
                self._logger.exception(
                    "cost_sensitivity_grid_point_failed",
                    extra={
                        "symbol": symbol,
                        "commission_rate": str(commission_rate),
                        "slippage_bps": str(slippage_bps),
                    },
                )
                continue

            completed += 1
            point_cost_level = cost_level(commission_rate, slippage_bps)
            for rule_id, bucket in by_rule.items():
                collected.setdefault(rule_id, []).append(
                    {
                        "commission_rate": str(commission_rate),
                        "slippage_bps": str(slippage_bps),
                        "cost_level": str(point_cost_level),
                        "expectancy": bucket["expectancy"],
                        "trade_count": bucket["trade_count"],
                    }
                )
            self._logger.info(
                "cost_sensitivity_grid_point_completed",
                extra={
                    "symbol": symbol,
                    "commission_rate": str(commission_rate),
                    "slippage_bps": str(slippage_bps),
                    "rule_count": len(by_rule),
                    "expectancies": {
                        rule_id: bucket["expectancy"] for rule_id, bucket in by_rule.items()
                    },
                },
            )

        summary_counts = {
            CLASSIFICATION_BREAKEVEN_FOUND: 0,
            CLASSIFICATION_NEVER_PROFITABLE: 0,
            CLASSIFICATION_SURVIVES_FULL_RANGE: 0,
        }
        by_rule_report: dict[str, dict[str, Any]] = {}
        for rule_id, points in collected.items():
            report = self._summarize_rule(rule_id, points)
            summary_counts[report["classification"]] += 1
            by_rule_report[rule_id] = report

        self._logger.info(
            "cost_sensitivity_sweep_completed",
            extra={
                "symbol": symbol,
                "grid_points_completed": completed,
                "grid_points_total": len(grid),
                "rule_count": len(by_rule_report),
                "breakeven_found": summary_counts[CLASSIFICATION_BREAKEVEN_FOUND],
                "never_profitable": summary_counts[CLASSIFICATION_NEVER_PROFITABLE],
                "survives_full_range": summary_counts[CLASSIFICATION_SURVIVES_FULL_RANGE],
            },
        )

        return {"grid_points_run": completed, "by_rule": by_rule_report}

    def _run_point(
        self,
        *,
        owner: Any,
        symbol: str,
        timeframe: str,
        range_start: datetime,
        range_end: datetime,
        commission_rate: Decimal,
        slippage_bps: Decimal,
        initial_capital: Decimal,
        point_index: int,
    ) -> dict[str, Any]:
        """One isolated backtest run at a single grid point; returns its by_rule."""
        account = Account.objects.create(
            name=f"CostSensitivity {symbol} point-{point_index}",
            owner=owner,
            is_default=False,
        )
        self._capital.deposit(account.id, initial_capital)
        run = BacktestRun(
            symbol=symbol,
            timeframe=timeframe,
            range_start=range_start,
            range_end=range_end,
            account=account,
            status="PENDING",
            commission_rate=commission_rate,
            slippage_bps=slippage_bps,
        )
        self._runs.create(run)
        self._runner.run(run.id)
        return self._stats.run_stats(run)["by_rule"]

    @staticmethod
    def _summarize_rule(rule_id: str, points: list[dict[str, Any]]) -> dict[str, Any]:
        """Build one rule's breakeven report from its successful grid points."""
        min_point = min(points, key=lambda point: Decimal(point["cost_level"]))
        max_point = max(points, key=lambda point: Decimal(point["cost_level"]))
        max_cost_level = Decimal(max_point["cost_level"])

        sweep_results = [
            {
                "cost_level": Decimal(point["cost_level"]),
                "expectancy": Decimal(point["expectancy"]),
            }
            for point in points
        ]
        breakeven = find_breakeven(sweep_results)

        if breakeven is not None:
            classification = CLASSIFICATION_BREAKEVEN_FOUND
            breakeven_commission = str(breakeven)
            breakeven_slippage = str(breakeven * _SLIPPAGE_BPS_PER_UNIT)
        elif all(row["expectancy"] < 0 for row in sweep_results):
            # Never had an edge to lose at any tested cost level — reporting a
            # fabricated zero or a wrong extrapolation is explicitly forbidden.
            classification = CLASSIFICATION_NEVER_PROFITABLE
            breakeven_commission = None
            breakeven_slippage = None
        else:
            # Edge survives the entire tested range; the range's upper bound
            # (the highest tested cost level) is the honest survivability floor.
            classification = CLASSIFICATION_SURVIVES_FULL_RANGE
            breakeven_commission = str(max_cost_level)
            breakeven_slippage = str(max_cost_level * _SLIPPAGE_BPS_PER_UNIT)

        return {
            "rule_id": rule_id,
            "expectancy_at_min_cost": min_point["expectancy"],
            "expectancy_at_max_cost": max_point["expectancy"],
            "breakeven_commission_rate": breakeven_commission,
            "breakeven_slippage_bps": breakeven_slippage,
            "classification": classification,
            "series": points,
        }