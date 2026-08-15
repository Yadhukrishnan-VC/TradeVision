"""Batch STRATEGY-EDGE-VALIDATION-1 — empirical per-rule edge evaluation.

This batch is a pure orchestrator, exactly like WALKFORWARD-VALIDATION-1 and
COST-SENSITIVITY-1: it introduces **no new persistence model** and reuses the
*unmodified* single-run engine and walk-forward engine end to end. For one
requested historical window it runs a single full-range backtest (its own
isolated funded account) once, reads per-rule metrics from
``BacktestStatsService.run_stats()["by_rule"]``, and runs one
``WalkForwardService.execute`` over the same range to capture the aggregate
out-of-sample distribution. It then applies one explicitly disclosed edge
criterion per rule and reports ``has_edge`` alongside the raw numbers so a
human can disagree with the threshold by reading the same data.

The edge criterion is deliberately simple and literal — **not** a novel
statistical significance test:

    rule *passes* (:code:`has_edge=True`) iff
        expectancy > 0
        AND profit_factor is not None
        AND profit_factor > 1.0
        AND trade_count >= MIN_TRADES

    trade_count < MIN_TRADES                 -> ``has_edge is None``
       ("insufficient data" — never ``False``; no evidence of edge is not
       evidence of no edge)

    otherwise                                 -> ``has_edge is False``

Two cost sensitivities are exposed: ``evaluate`` runs the report at one
``(commission_rate, slippage_bps)`` pair, and ``compare_costs`` runs it at the
existing zero-cost default plus one caller-supplied realistic setting and
reports, per rule, ``has_edge`` at both settings plus a ``flipped`` boolean
(whether the verdict changed between the two).

Trading correctness: this batch adds zero temporal logic. Every run goes
through the same ``bind_simulated_time``-wrapped, next-bar-fill,
gap-through-stop-loss engine as every existing backtest; the only novelty is
orchestrating the existing services in sequence and reading ``by_rule`` /
walk-forward outputs. ``metrics.py``, ``services.py`` and
``walk_forward_service.py`` are called, never modified.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from apps.accounts.infrastructure.models import Account
from apps.backtesting.application.walk_forward_service import WalkForwardService
from apps.backtesting.models import BacktestRun
from apps.backtesting.repository import BacktestRunRepository
from apps.backtesting.services import BacktestRunnerService, BacktestStatsService
from apps.portfolio.application.capital_service import CapitalService
from core.services import BaseService

#: Minimum number of trades a rule must produce before the disclosed edge
#: criterion is allowed to pronounce a True/False verdict. Below this the rule
#: is reported as ``has_edge=None`` (insufficient data), never ``False``.
MIN_TRADES = 10

#: The literal, disclosed edge criterion applied per rule. Kept as plain data
#: so the response can echo back exactly what threshold was applied.
EDGE_CRITERION: dict[str, Any] = {
    "expectancy_greater_than_zero": True,
    "profit_factor_not_none": True,
    "profit_factor_greater_than_one": Decimal("1.0"),
    "min_trades": MIN_TRADES,
    "insufficient_data": "has_edge=None when trade_count < min_trades (never False)",
}


def _apply_edge_criterion(bucket: dict[str, Any]) -> bool | None:
    """Apply the disclosed edge criterion to one ``by_rule`` bucket.

    `True`/`False`/`None` semantics are documented at module level; the
    ``by_rule`` bucket is exactly the raw one produced by :meth:`run_stats` —
    this function only reads from it and never modifies it.
    """
    trade_count = int(bucket["trade_count"])
    if trade_count < MIN_TRADES:
        return None
    if Decimal(bucket["expectancy"]) <= Decimal(0):
        return False
    profit_factor = bucket["profit_factor"]
    if profit_factor is None:
        return False
    return Decimal(profit_factor) > Decimal("1.0")


class EdgeValidationService(BaseService):
    """Runs the single-run + walk-forward engines and reports per-rule edge."""

    def __init__(
        self,
        *,
        runner: BacktestRunnerService | None = None,
        stats: BacktestStatsService | None = None,
        run_repo: BacktestRunRepository | None = None,
        capital: CapitalService | None = None,
        walk_forward: WalkForwardService | None = None,
    ) -> None:
        super().__init__()
        self._runner = runner or BacktestRunnerService()
        self._stats = stats or BacktestStatsService()
        self._runs = run_repo or BacktestRunRepository()
        self._capital = capital or CapitalService()
        self._walk_forward = walk_forward

    def evaluate(
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
        commission_rate: Decimal = Decimal(0),
        slippage_bps: Decimal = Decimal(0),
        initial_capital: Decimal = Decimal(1000000),
    ) -> dict[str, Any]:
        """Evaluate every rule that traded over ``[range_start, range_end]``.

        Runs one ordinary full-range backtest to obtain ``by_rule`` /
        ``by_regime`` / IS-OOS metrics (``run_stats`` output passed through
        unchanged), then one ``WalkForwardService.execute`` over the same
        range (its aggregate OOS distribution passed through unchanged). For
        each rule that traded, the response carries the disclosed edge verdict
        (``has_edge``) plus the raw expectancy / profit-factor / Sharpe /
        Sortino / max-drawdown / trade_count so the verdict is verifiable from
        the same numbers used to derive it.
        """
        stats = self._run_full_range(
            owner=owner,
            symbol=symbol,
            timeframe=timeframe,
            range_start=range_start,
            range_end=range_end,
            in_sample_ratio=in_sample_ratio,
            commission_rate=commission_rate,
            slippage_bps=slippage_bps,
            initial_capital=initial_capital,
        )

        walk_forward_service = self._walk_forward or WalkForwardService(
            runner=self._runner,
            stats=self._stats,
            run_repo=self._runs,
            capital=self._capital,
        )
        walk_forward = walk_forward_service.execute(
            owner=owner,
            symbol=symbol,
            timeframe=timeframe,
            range_start=range_start,
            range_end=range_end,
            window_size_days=window_size_days,
            step_size_days=step_size_days,
            in_sample_ratio=in_sample_ratio,
            initial_capital=initial_capital,
            commission_rate=commission_rate,
            slippage_bps=slippage_bps,
        )

        by_rule: dict[str, dict[str, Any]] = {}
        for rule_id, bucket in stats["by_rule"].items():
            by_rule[rule_id] = self._single_rule_report(rule_id, bucket)

        self._logger.info(
            "edge_validation_single_run_completed",
            extra={
                "symbol": symbol,
                "timeframe": timeframe,
                "rule_count": len(by_rule),
                "passed": sum(1 for report in by_rule.values() if report["has_edge"] is True),
            },
        )

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "range_start": range_start.isoformat(),
            "range_end": range_end.isoformat(),
            "window_size_days": window_size_days,
            "step_size_days": step_size_days,
            "in_sample_ratio": str(in_sample_ratio),
            "commission_rate": str(commission_rate),
            "slippage_bps": str(slippage_bps),
            "edge_criterion": EDGE_CRITERION,
            "single_run": stats,
            "walk_forward": walk_forward,
            "by_rule": by_rule,
        }

    def compare_costs(
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
        realistic_commission_rate: Decimal = Decimal("0.0003"),
        realistic_slippage_bps: Decimal = Decimal("5.0"),
        initial_capital: Decimal = Decimal(1000000),
    ) -> dict[str, Any]:
        """Compare ``has_edge`` at the zero-cost baseline vs a realistic cost.

        Re-runs the full evaluation at ``(commission_rate=0, slippage_bps=0)``
        and at the caller-supplied realistic setting, and per rule reports
        ``has_edge`` at both settings plus a ``flipped`` boolean (True iff the
        verdict changed between the two — never flipping on an
        insufficient-data ``None``). Both full reports are embedded so the raw
        numbers at each setting stay verifiable.
        """
        baseline = self.evaluate(
            owner=owner,
            symbol=symbol,
            timeframe=timeframe,
            range_start=range_start,
            range_end=range_end,
            window_size_days=window_size_days,
            step_size_days=step_size_days,
            in_sample_ratio=in_sample_ratio,
            commission_rate=Decimal(0),
            slippage_bps=Decimal(0),
            initial_capital=initial_capital,
        )
        realistic = self.evaluate(
            owner=owner,
            symbol=symbol,
            timeframe=timeframe,
            range_start=range_start,
            range_end=range_end,
            window_size_days=window_size_days,
            step_size_days=step_size_days,
            in_sample_ratio=in_sample_ratio,
            commission_rate=realistic_commission_rate,
            slippage_bps=realistic_slippage_bps,
            initial_capital=initial_capital,
        )

        by_rule: dict[str, dict[str, Any]] = {}
        for rule_id in sorted(baseline["by_rule"].keys() | realistic["by_rule"].keys()):
            baseline_report = baseline["by_rule"].get(rule_id)
            realistic_report = realistic["by_rule"].get(rule_id)
            baseline_has_edge = (
                baseline_report["has_edge"] if baseline_report is not None else None
            )
            realistic_has_edge = (
                realistic_report["has_edge"] if realistic_report is not None else None
            )
            by_rule[rule_id] = {
                "rule_id": rule_id,
                "baseline_has_edge": baseline_has_edge,
                "realistic_cost_has_edge": realistic_has_edge,
                "flipped": (
                    baseline_has_edge is not None
                    and realistic_has_edge is not None
                    and baseline_has_edge != realistic_has_edge
                ),
                "baseline": baseline_report,
                "realistic_cost": realistic_report,
            }

        self._logger.info(
            "edge_validation_completed",
            extra={
                "symbol": symbol,
                "timeframe": timeframe,
                "rule_count": len(by_rule),
                "baseline_passed": sum(
                    1 for report in by_rule.values() if report["baseline_has_edge"] is True
                ),
                "realistic_cost_passed": sum(
                    1
                    for report in by_rule.values()
                    if report["realistic_cost_has_edge"] is True
                ),
                "flipped_count": sum(1 for report in by_rule.values() if report["flipped"]),
            },
        )

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "range_start": range_start.isoformat(),
            "range_end": range_end.isoformat(),
            "window_size_days": window_size_days,
            "step_size_days": step_size_days,
            "in_sample_ratio": str(in_sample_ratio),
            "realistic_commission_rate": str(realistic_commission_rate),
            "realistic_slippage_bps": str(realistic_slippage_bps),
            "edge_criterion": EDGE_CRITERION,
            "baseline": baseline,
            "realistic_cost": realistic,
            "by_rule": by_rule,
        }

    def _run_full_range(
        self,
        *,
        owner: Any,
        symbol: str,
        timeframe: str,
        range_start: datetime,
        range_end: datetime,
        in_sample_ratio: Decimal,
        commission_rate: Decimal,
        slippage_bps: Decimal,
        initial_capital: Decimal,
    ) -> dict[str, Any]:
        """One isolated (account + run) full-range backtest; returns run_stats."""
        account = Account.objects.create(
            name=f"EdgeValidation {symbol} {range_start.date()}",
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
            in_sample_ratio=in_sample_ratio,
        )
        self._runs.create(run)
        self._runner.run(run.id)
        return self._stats.run_stats(run)

    @staticmethod
    def _single_rule_report(rule_id: str, bucket: dict[str, Any]) -> dict[str, Any]:
        """The raw ``by_rule`` numbers for one rule plus its disclosed verdict.

        The underlying numbers are passed through from ``run_stats`` verbatim;
        only ``has_edge`` is derived (via :func:`_apply_edge_criterion`).
        """
        return {
            "rule_id": rule_id,
            "trade_count": bucket["trade_count"],
            "win_rate": bucket["win_rate"],
            "expectancy": bucket["expectancy"],
            "profit_factor": bucket["profit_factor"],
            "sharpe_ratio": bucket["sharpe_ratio"],
            "sortino_ratio": bucket["sortino_ratio"],
            "max_drawdown_pct": bucket["max_drawdown_pct"],
            "has_edge": _apply_edge_criterion(bucket),
        }