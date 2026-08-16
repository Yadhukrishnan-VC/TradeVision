"""ADR-029 — Rule firing validation gate: verdict computation.

``RuleValidationService`` turns a completed ``BacktestRun`` into per-rule,
per-regime go/no-go verdicts written into ``RuleConfig.validated_regimes``.

It deliberately reuses existing pure attribution/metrics helpers
(``group_fills_by_rule``, ``apps.backtesting.domain.metrics``) instead of
re-implementing any performance math, and never auto-enables a rule: a
``GO`` verdict makes a rule *eligible* for live firing, not *live*. Whether
``RuleConfig.enabled`` is ``True`` stays a separate, explicit human decision.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from apps.backtesting.domain.attribution import (
    group_fills_by_rule,
)
from apps.backtesting.domain.metrics import (
    calculate_expectancy,
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_sharpe_ratio,
)
from apps.backtesting.infrastructure.rule_attribution_repository import (
    RuleAttributionRepository,
)
from apps.backtesting.models import BacktestRun, BacktestRunStatus
from apps.rule_engine.infrastructure.models import RuleConfig
from apps.rule_engine.infrastructure.repositories import RuleConfigRepository
from core.services import BaseService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ADR-029 §4 — threshold logic (v1 defaults, revisit with real risk tolerance)
# ---------------------------------------------------------------------------
MIN_TRADE_COUNT = 30
MIN_EXPECTANCY = Decimal(0)
MIN_PROFIT_FACTOR = Decimal("1.3")
MAX_DRAWDOWN_PCT = Decimal(20)

VERDICT_GO = "GO"
VERDICT_NO_GO = "NO_GO"
VERDICT_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

UNKNOWN_REGIME = "UNKNOWN"

_DEFAULT_INITIAL_EQUITY = Decimal("100000.00")


def _net_trade_pnl(
    order: Any,
    comm_rate: Decimal,
    slip_bps: Decimal,
) -> Decimal:
    """Net realised PnL for one order after commission and slippage.

    Mirrors the per-order cost model used by ``BacktestStatsService.run_stats``
    so validation and stats agree on what a trade actually earned.
    """
    direction = Decimal(1) if str(order.side).upper() == "LONG" else Decimal(-1)
    avg_fill = order.avg_fill_price or Decimal(0)
    raw_pnl = (avg_fill - order.entry_price) * order.filled_quantity * direction
    order_cost = (
        (order.filled_quantity * avg_fill * comm_rate)
        + (order.filled_quantity * avg_fill * (slip_bps / Decimal(10000)))
    )
    return raw_pnl - order_cost


def _bucket_from_orders(
    orders: list[Any],
    comm_rate: Decimal,
    slip_bps: Decimal,
    initial_equity: Decimal,
) -> dict[str, Any]:
    """Aggregate one ``(rule_id, regime)`` group's trades into metric inputs."""
    trade_count = len(orders)
    win_count = 0
    loss_count = 0
    gross_profit = Decimal(0)
    gross_loss = Decimal(0)
    total_costs = Decimal(0)
    equity_curve: list[Decimal] = [initial_equity]
    returns: list[Decimal] = []

    current_equity = initial_equity
    for order in orders:
        avg_fill = order.avg_fill_price or Decimal(0)
        cost = (
            (order.filled_quantity * avg_fill * comm_rate)
            + (order.filled_quantity * avg_fill * (slip_bps / Decimal(10000)))
        )
        net_pnl = _net_trade_pnl(order, comm_rate, slip_bps)
        total_costs += cost
        if net_pnl > Decimal(0):
            win_count += 1
            gross_profit += net_pnl
        elif net_pnl < Decimal(0):
            loss_count += 1
            gross_loss += abs(net_pnl)

        prev_eq = current_equity
        current_equity += net_pnl
        equity_curve.append(current_equity)
        if prev_eq > Decimal(0):
            returns.append((current_equity - prev_eq) / prev_eq)

    win_rate = (
        Decimal(win_count) / Decimal(trade_count) if trade_count > 0 else Decimal(0)
    )
    avg_win = gross_profit / Decimal(win_count) if win_count > 0 else Decimal(0)
    avg_loss = gross_loss / Decimal(loss_count) if loss_count > 0 else Decimal(0)
    avg_cost = total_costs / Decimal(trade_count) if trade_count > 0 else Decimal(0)

    max_dd_pct, _max_dd_amt = calculate_max_drawdown(equity_curve)

    return {
        "trade_count": trade_count,
        "expectancy": calculate_expectancy(win_rate, avg_win, avg_loss, avg_cost),
        "profit_factor": calculate_profit_factor(gross_profit, gross_loss, total_costs),
        "max_drawdown_pct": max_dd_pct,
        "sharpe_ratio": calculate_sharpe_ratio(returns),
    }


def _verdict_for_bucket(regime: str, bucket: dict[str, Any]) -> str:
    """ADR-029 §4 verdict: INSUFFICIENT_DATA / GO / NO_GO.

    ``UNKNOWN`` regime never reaches the numeric checks — untagged executions
    are not gate-eligible at all. ``None`` profit factor (no profit) or
    ``None`` Sharpe (insufficient samples / zero variance) never pass; a
    ``None`` Sharpe is non-blocking in the sense that it never *counts toward*
    a pass, it simply can't be the deciding factor either.
    """
    if regime == UNKNOWN_REGIME:
        return VERDICT_NO_GO

    if bucket["trade_count"] < MIN_TRADE_COUNT:
        return VERDICT_INSUFFICIENT_DATA

    pf = bucket["profit_factor"]
    if (
        bucket["expectancy"] > MIN_EXPECTANCY
        and pf is not None
        and pf > MIN_PROFIT_FACTOR
        and bucket["max_drawdown_pct"] < MAX_DRAWDOWN_PCT
    ):
        return VERDICT_GO
    return VERDICT_NO_GO


class RuleValidationService(BaseService):
    """Compute and persist per-rule/per-regime verdicts for a completed run."""

    def __init__(
        self,
        config_repo: RuleConfigRepository | None = None,
        attribution_repo: RuleAttributionRepository | None = None,
    ) -> None:
        super().__init__()
        self._config_repo = config_repo or RuleConfigRepository()
        self._attribution_repo = attribution_repo or RuleAttributionRepository()

    def validate_run(self, run: BacktestRun) -> dict[str, Any]:
        """Validate one completed ``BacktestRun`` and persist verdicts.

        Returns a summary ``{rule_id: {regime: verdict, ...}}`` for
        observability; raises ``ValueError`` if the run is not COMPLETED.
        """
        if run.status != BacktestRunStatus.COMPLETED:
            raise ValueError(
                f"RuleValidationService requires a COMPLETED BacktestRun; "
                f"got {run.status} for run={run.id}"
            )

        comm_rate = Decimal(str(run.commission_rate or "0"))
        slip_bps = Decimal(str(run.slippage_bps or "0"))

        from apps.execution.infrastructure.models import Fill, Order
        from apps.portfolio.infrastructure.models import AccountCapitalState
        from apps.rule_engine.infrastructure.models import RuleExecution

        orders = list(
            Order.objects.filter(account_id=run.account_id).order_by("created_at")
        )
        fills = list(
            Fill.objects.filter(order__account_id=run.account_id).order_by("created_at")
        )
        capital = AccountCapitalState.objects.filter(
            account_id=run.account_id
        ).first()
        initial_equity = capital.equity if capital else _DEFAULT_INITIAL_EQUITY

        correlation_ids = {
            order.correlation_id for order in orders if order.correlation_id
        }
        rule_executions = self._attribution_repo.get_rule_executions(correlation_ids)

        # Regime map: fill's order -> correlation_id -> RuleExecution.trigger_data.
        regime_by_correlation: dict[str, str] = {}
        for execution in RuleExecution.objects.filter(
            analysis_event_id__in=correlation_ids
        ).only("analysis_event_id", "trigger_data"):
            regime = (execution.trigger_data or {}).get("regime")
            if regime:
                regime_by_correlation[str(execution.analysis_event_id)] = str(regime)

        order_by_id = {str(order.id): order for order in orders}
        fills_by_rule = group_fills_by_rule(fills, rule_executions, order_by_id)

        summary: dict[str, dict[str, str]] = {}
        for rule_id, rule_fills in fills_by_rule.items():
            # Sub-group the rule's fills by regime. Each distinct order is a
            # single trade; dedupe so a multi-fill order is not counted twice.
            regime_orders: dict[str, list[Any]] = {}
            seen_orders: set[str] = set()
            for fill in rule_fills:
                order = order_by_id.get(str(fill.order_id))
                if order is None or str(order.id) in seen_orders:
                    continue
                seen_orders.add(str(order.id))
                regime = regime_by_correlation.get(str(order.correlation_id))
                regime = regime or UNKNOWN_REGIME
                regime_orders.setdefault(regime, []).append(order)

            rule_summary: dict[str, str] = {}
            for regime, regime_order_list in regime_orders.items():
                bucket = _bucket_from_orders(
                    regime_order_list, comm_rate, slip_bps, initial_equity
                )
                verdict = _verdict_for_bucket(regime, bucket)
                self._write_verdict(rule_id, regime, verdict, bucket, run)
                rule_summary[regime] = verdict
                logger.info(
                    "rule_validation_verdict_written",
                    extra={
                        "rule_id": rule_id,
                        "regime": regime,
                        "status": verdict,
                        "trade_count": bucket["trade_count"],
                        "backtest_run_id": str(run.id),
                    },
                )
            summary[rule_id] = rule_summary

        logger.info(
            "rule_validation_completed",
            extra={"run_id": str(run.id), "rules": len(summary)},
        )
        return summary

    def _write_verdict(
        self,
        rule_id: str,
        regime: str,
        verdict: str,
        bucket: dict[str, Any],
        run: BacktestRun,
    ) -> None:
        """Persist one verdict into ``RuleConfig.validated_regimes``.

        Creates the ``RuleConfig`` row with ``enabled=False`` explicitly when
        none exists (ADR-029 §3: backtesting alone never implies live firing).
        ``enabled`` is never flipped to ``True`` here.
        """
        verdict_payload = {
            "status": verdict,
            "expectancy": str(bucket["expectancy"]),
            "profit_factor": (
                str(bucket["profit_factor"])
                if bucket["profit_factor"] is not None
                else None
            ),
            "sharpe_ratio": (
                str(bucket["sharpe_ratio"])
                if bucket["sharpe_ratio"] is not None
                else None
            ),
            "max_drawdown_pct": str(bucket["max_drawdown_pct"]),
            "trade_count": bucket["trade_count"],
            "backtest_run_id": str(run.id),
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

        config = self._config_repo.get_by_rule_id(rule_id)
        if config is None:
            config = RuleConfig(rule_id=rule_id, enabled=False)
            config = self._config_repo.create(config)

        current = dict(config.validated_regimes or {})
        current[regime] = verdict_payload
        config.validated_regimes = current
        self._config_repo.update(config)