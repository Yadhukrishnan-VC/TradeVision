"""Batch M3 & M3.8 — Backtest runner and strategy edge performance statistics.

The runner replays historical ``TASnapshot`` payloads through the *real*
event-driven pipeline (``TechnicalAnalysisIngestionService`` -> EventBus ->
intelligence -> rule_engine -> risk_management -> execution -> PaperBroker)
one bar at a time.

Execution Realism (Batch M3.8):
* Fills occur on the NEXT bar's open price to eliminate look-ahead fill timing.
* Configurable commission rates and basis-point slippage are applied during execution.
* Complete quantitative performance suite calculated: Net P&L, Expectancy, Profit Factor,
  Max Drawdown, Sharpe Ratio, Sortino Ratio, Buy-and-Hold Benchmark, and IS/OOS split.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.conf import settings

from apps.backtesting.domain.attribution import (
    build_correlation_to_rule_map,
    group_fills_by_rule,
)
from apps.backtesting.domain.metrics import (
    calculate_benchmark_return,
    calculate_expectancy,
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
)
from apps.backtesting.infrastructure.rule_attribution_repository import (
    RuleAttributionRepository,
)
from apps.backtesting.models import BacktestRun, BacktestRunStatus
from apps.backtesting.repository import BacktestRunRepository
from apps.common.domain.value_objects import IdempotencyKey
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.technical_analysis.application.services import TechnicalAnalysisIngestionService
from apps.technical_analysis.infrastructure.repositories import TASnapshotRepository
from core.clock import bind_simulated_time, get_clock
from core.execution_context import (
    bind_account_override,
    bind_backtest_execution,
)
from core.services import BaseService

logger = logging.getLogger(__name__)


def _correlation_id_for(run_id: uuid.UUID, snapshot_id: uuid.UUID) -> uuid.UUID:
    """Deterministic, traceable correlation id for one historical bar."""
    digest = IdempotencyKey.generate(str(run_id), str(snapshot_id)).value
    return uuid.UUID(hex=digest[:32])


class BacktestRunnerService(BaseService):
    """Orchestrates one backtest run through the production event pipeline."""

    def __init__(
        self,
        run_repo: BacktestRunRepository | None = None,
        ta_repo: TASnapshotRepository | None = None,
    ) -> None:
        super().__init__()
        self._runs = run_repo or BacktestRunRepository()
        self._ta = ta_repo or TASnapshotRepository()

    def run(self, run_id: uuid.UUID) -> dict[str, str]:
        """Execute (or resume) the run; returns its final status."""
        run = self._runs.get_by_id(run_id)
        if run is None:
            return {"status": "MISSING", "run_id": str(run_id)}
        if run.status == BacktestRunStatus.COMPLETED:
            return {"status": "ALREADY_COMPLETED", "run_id": str(run_id)}
        if not getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
            reason = (
                "Backtest replay requires CELERY_TASK_ALWAYS_EAGER=True "
                "(simulation contextvars do not cross Celery worker processes)."
            )
            self._runs.mark_failed(run_id, reason)
            return {"status": "FAILED", "run_id": str(run_id), "reason": reason}

        now = get_clock().now()
        self._runs.mark_running(run_id, started_at=now)
        try:
            pending = self._pending_snapshots(run)
            for index, snapshot in enumerate(pending):
                correlation_id = _correlation_id_for(run.id, snapshot.id)

                # Execute any pending orders from prior bars at THIS bar's open price.
                # RESEARCH-INTEGRITY-2 (same-candle/look-ahead fill): the fill
                # price must be the *real* next-bar open. Falling back to this
                # bar's close would fill at a price not yet known at the open —
                # a look-ahead. If the open is missing/invalid we fail safe and
                # leave the orders pending (the final-bar flush or a later bar
                # can still fill them).
                raw = snapshot.raw_payload or {}
                bar_open = self._extract_decimal(raw.get("open"))
                if index > 0 and bar_open is not None:
                    self._fill_pending_orders(
                        run=run,
                        fill_price=bar_open,
                        timestamp=snapshot.snapshot_timestamp,
                    )

                with bind_account_override(run.account_id), bind_simulated_time(
                    snapshot.snapshot_timestamp
                ), bind_backtest_execution(
                    commission_rate=run.commission_rate,
                    slippage_bps=run.slippage_bps,
                    defer_fills=True,
                ):
                    self._ingest(snapshot.raw_payload, correlation_id)

                self._runs.update_cursor(run_id, snapshot.id)

            # Fill remaining pending orders on final bar using final bar close
            if pending:
                last = pending[-1]
                last_raw = last.raw_payload or {}
                last_price = self._extract_decimal(last_raw.get("close") or last_raw.get("open"))
                if last_price is not None:
                    self._fill_pending_orders(
                        run=run,
                        fill_price=last_price,
                        timestamp=last.snapshot_timestamp,
                    )

            self._runs.mark_completed(run_id, completed_at=get_clock().now())
            return {
                "status": "COMPLETED",
                "run_id": str(run_id),
                "bars_processed": str(len(pending)),
            }
        except Exception as exc:
            logger.exception(
                "backtest_run_failed",
                extra={"run_id": str(run_id), "symbol": run.symbol},
            )
            self._runs.mark_failed(run_id, str(exc))
            return {"status": "FAILED", "run_id": str(run_id), "reason": str(exc)}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _pending_snapshots(self, run: BacktestRun) -> list[Any]:
        """Historical bars in chronological order, minus the already-consumed cursor."""
        snapshots = self._ta.find_in_range(
            run.symbol, run.range_start, run.range_end, timeframe=run.timeframe
        )
        cursor = run.last_processed_snapshot_id
        if cursor is None:
            return snapshots
        for index, snapshot in enumerate(snapshots):
            if snapshot.id == cursor:
                return snapshots[index + 1 :]
        return snapshots

    def _ingest(self, raw_payload: dict[str, Any], correlation_id: uuid.UUID) -> None:
        """Replay one historical payload through the real ingestion service."""
        service = TechnicalAnalysisIngestionService(
            repository=TASnapshotRepository(),
            event_bus=get_event_bus(),
        )
        service.ingest(raw_payload, correlation_id=correlation_id)

    def _fill_pending_orders(
        self,
        run: BacktestRun,
        fill_price: Decimal,
        timestamp: Any,
    ) -> None:
        from apps.execution.application.execution_engine import ExecutionEngine
        from apps.execution.domain.value_objects import FillMode, OrderStatus
        from apps.execution.infrastructure.brokers.paper_broker import PaperBroker
        from apps.execution.infrastructure.models import Order

        pending_orders = list(
            Order.objects.filter(
                account_id=run.account_id,
                status__in=[
                    OrderStatus.CREATED.value,
                    OrderStatus.SUBMITTED.value,
                    OrderStatus.ACKNOWLEDGED.value,
                ],
            )
        )
        if not pending_orders:
            return

        broker = PaperBroker(
            mode=FillMode.FULL_FILL,
            fill_price=fill_price,
            commission_rate=run.commission_rate,
            slippage_bps=run.slippage_bps,
        )

        with bind_account_override(run.account_id), bind_simulated_time(
            timestamp
        ), bind_backtest_execution(
            commission_rate=run.commission_rate,
            slippage_bps=run.slippage_bps,
            next_bar_open=fill_price,
        ):
            engine = ExecutionEngine(broker=broker)
            for order in pending_orders:
                engine.execute_order(order.id)

    @staticmethod
    def _extract_decimal(value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None


class BacktestStatsService(BaseService):
    """Read-only aggregation & quantitative edge analysis of a backtest run."""

    def run_stats(self, run: BacktestRun) -> dict[str, Any]:
        from apps.execution.infrastructure.models import ExecutionRequest, Fill, Order
        from apps.portfolio.infrastructure.models import AccountCapitalState

        orders = list(
            Order.objects.filter(account_id=run.account_id).order_by("created_at")
        )
        fills = list(
            Fill.objects.filter(order__account_id=run.account_id).order_by("created_at")
        )
        capital = AccountCapitalState.objects.filter(account_id=run.account_id).first()
        risk_rejected_count = ExecutionRequest.objects.filter(
            account_id=run.account_id, status__startswith="REJECTED"
        ).count()

        regime_by_correlation = self._resolve_regimes(orders)
        regime_buckets: dict[str, dict[str, Any]] = {}
        missing_regime_count = 0

        # Per-rule attribution (Batch M4.5): each Order carries a correlation_id
        # equal to the RuleExecution.analysis_event_id of the rule that fired it.
        order_by_id = {str(order.id): order for order in orders}
        correlation_ids = {order.correlation_id for order in orders if order.correlation_id}
        rule_executions = RuleAttributionRepository().get_rule_executions(correlation_ids)
        rule_by_correlation = build_correlation_to_rule_map(rule_executions)
        rule_buckets: dict[str, dict[str, Any]] = {}
        unattributed_trade_count = 0

        gross_profit = Decimal("0")
        gross_loss = Decimal("0")
        total_costs = Decimal("0")
        total_slippage = Decimal("0")
        win_count = 0
        loss_count = 0

        comm_rate = Decimal(str(run.commission_rate or "0"))
        slip_bps = Decimal(str(run.slippage_bps or "0"))

        # Execution realism (Risk Sophistication batch): when configured, use
        # the realistic NSE cost model (STT, brokerage, exchange charges, GST,
        # SEBI fee, stamp duty + size-dependent impact) instead of the flat
        # commission/slippage pair. The flat path is the untouched default.
        from apps.backtesting.domain.nse_costs import (
            compute_trade_cost,
            nse_cost_model_from_settings,
        )

        nse_model = (
            nse_cost_model_from_settings()
            if getattr(settings, "BACKTEST_COST_MODEL", "flat") == "nse"
            else None
        )

        if nse_model is None:
            for fill in fills:
                fee = fill.quantity * fill.price * comm_rate
                slip_impact = fill.quantity * fill.price * (slip_bps / Decimal("10000"))
                total_costs += fee + slip_impact
                total_slippage += slip_impact

        # RESEARCH-INTEGRITY-1 (timestamp leakage / IS-OOS contamination):
        # ``order.created_at`` is the WALL-CLOCK creation time (audit row), not
        # the bar's simulated time, so it must never drive the IS/OOS split.
        # The simulated trade time is the first fill's ``occurred_at`` (bound to
        # ``snapshot_timestamp`` by the runner). Orders without a fill fall back
        # to their created_at so synthetic/partial fixtures stay deterministic.
        first_fill_at: dict[str, datetime] = {}
        for fill in fills:
            key = str(fill.order_id)
            if key not in first_fill_at or fill.occurred_at < first_fill_at[key]:
                first_fill_at[key] = fill.occurred_at

        trades: list[dict[str, Any]] = []
        initial_eq = capital.equity if capital else Decimal("100000.00")
        equity_curve: list[Decimal] = [initial_eq]
        daily_returns: list[Decimal] = []

        current_equity = initial_eq

        # IS/OOS static split (Batch IS-OOS-METRICS-1): the run's date range is
        # divided once by in_sample_ratio; trades before split_ts are the
        # in-sample half, the rest out-of-sample. Same split_ts the old
        # partition pass used, computed earlier so per-bucket equity/returns can
        # be accumulated inline with the other bucket passes.
        total_seconds = (run.range_end - run.range_start).total_seconds()
        split_seconds = total_seconds * float(run.in_sample_ratio)
        split_ts = run.range_start.timestamp() + split_seconds

        is_bucket = {
            "trade_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "gross_profit": Decimal("0"),
            "gross_loss": Decimal("0"),
            "total_costs": Decimal("0"),
            "equity_curve": [initial_eq],
            "returns": [],
            "trades": [],
        }
        oos_bucket = {
            "trade_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "gross_profit": Decimal("0"),
            "gross_loss": Decimal("0"),
            "total_costs": Decimal("0"),
            "equity_curve": [initial_eq],
            "returns": [],
            "trades": [],
        }

        for order in orders:
            direction = Decimal("1") if str(order.side).upper() == "LONG" else Decimal("-1")
            avg_fill = order.avg_fill_price or Decimal("0")
            raw_pnl = (avg_fill - order.entry_price) * order.filled_quantity * direction

            if nse_model is not None:
                order_cost = self._nse_cost_for_order(order, nse_model, compute_trade_cost)
                total_costs += order_cost
                total_slippage += self._nse_impact_for_order(
                    order, nse_model, compute_trade_cost
                )
            else:
                order_cost = (
                    (order.filled_quantity * avg_fill * comm_rate)
                    + (order.filled_quantity * avg_fill * (slip_bps / Decimal("10000")))
                )
            net_trade_pnl = raw_pnl - order_cost

            if net_trade_pnl > Decimal("0"):
                win_count += 1
                gross_profit += net_trade_pnl
            elif net_trade_pnl < Decimal("0"):
                loss_count += 1
                gross_loss += abs(net_trade_pnl)

            trade_entry = {
                "order_id": str(order.id),
                "symbol": order.symbol,
                "side": order.side,
                "quantity": str(order.quantity),
                "entry_price": str(order.entry_price),
                "avg_fill_price": str(avg_fill),
                "filled_quantity": str(order.filled_quantity),
                "status": order.status,
                "realized_pnl": str(raw_pnl),
                "net_pnl": str(net_trade_pnl),
                "transaction_cost": str(order_cost),
                "created_at": order.created_at.isoformat() if order.created_at else "",
            }

            regime = regime_by_correlation.get(order.correlation_id)
            if regime:
                bucket = regime_buckets.setdefault(
                    regime,
                    {
                        "trade_count": 0,
                        "win_count": 0,
                        "loss_count": 0,
                        "gross_profit": Decimal("0"),
                        "gross_loss": Decimal("0"),
                        "total_costs": Decimal("0"),
                        "equity_curve": [initial_eq],
                        "returns": [],
                        "trades": [],
                    },
                )
                bucket["trade_count"] += 1
                bucket["total_costs"] += order_cost
                if net_trade_pnl > Decimal("0"):
                    bucket["win_count"] += 1
                    bucket["gross_profit"] += net_trade_pnl
                elif net_trade_pnl < Decimal("0"):
                    bucket["loss_count"] += 1
                    bucket["gross_loss"] += abs(net_trade_pnl)
                bucket["trades"].append(trade_entry)
                prev_bucket_eq = bucket["equity_curve"][-1]
                next_bucket_eq = prev_bucket_eq + net_trade_pnl
                bucket["equity_curve"].append(next_bucket_eq)
                if prev_bucket_eq > Decimal("0"):
                    bucket["returns"].append(
                        (next_bucket_eq - prev_bucket_eq) / prev_bucket_eq
                    )
            else:
                missing_regime_count += 1

            rule_id = rule_by_correlation.get(str(order.correlation_id))
            if rule_id:
                rule_bucket = rule_buckets.setdefault(
                    rule_id,
                    {
                        "trade_count": 0,
                        "win_count": 0,
                        "loss_count": 0,
                        "gross_profit": Decimal("0"),
                        "gross_loss": Decimal("0"),
                        "total_costs": Decimal("0"),
                        "equity_curve": [initial_eq],
                        "returns": [],
                        "trades": [],
                    },
                )
                rule_bucket["trade_count"] += 1
                rule_bucket["total_costs"] += order_cost
                if net_trade_pnl > Decimal("0"):
                    rule_bucket["win_count"] += 1
                    rule_bucket["gross_profit"] += net_trade_pnl
                elif net_trade_pnl < Decimal("0"):
                    rule_bucket["loss_count"] += 1
                    rule_bucket["gross_loss"] += abs(net_trade_pnl)
                rule_bucket["trades"].append(trade_entry)
                prev_rule_eq = rule_bucket["equity_curve"][-1]
                next_rule_eq = prev_rule_eq + net_trade_pnl
                rule_bucket["equity_curve"].append(next_rule_eq)
                if prev_rule_eq > Decimal("0"):
                    rule_bucket["returns"].append((next_rule_eq - prev_rule_eq) / prev_rule_eq)
            else:
                unattributed_trade_count += 1

            # IS/OOS partition: same equity-curve/returns accumulation the
            # regime and rule buckets above do, for each half of the split.
            # The trade's time is its first fill's simulated ``occurred_at``
            # (never the wall-clock ``order.created_at`` — see RESEARCH-INTEGRITY-1).
            trade_ts = first_fill_at.get(str(order.id)) or order.created_at
            if trade_ts and trade_ts.timestamp() <= split_ts:
                split_bucket = is_bucket
            else:
                split_bucket = oos_bucket
            split_bucket["trade_count"] += 1
            split_bucket["total_costs"] += order_cost
            if net_trade_pnl > Decimal("0"):
                split_bucket["win_count"] += 1
                split_bucket["gross_profit"] += net_trade_pnl
            elif net_trade_pnl < Decimal("0"):
                split_bucket["loss_count"] += 1
                split_bucket["gross_loss"] += abs(net_trade_pnl)
            split_bucket["trades"].append(trade_entry)
            prev_split_eq = split_bucket["equity_curve"][-1]
            next_split_eq = prev_split_eq + net_trade_pnl
            split_bucket["equity_curve"].append(next_split_eq)
            if prev_split_eq > Decimal("0"):
                split_bucket["returns"].append((next_split_eq - prev_split_eq) / prev_split_eq)

            current_equity += net_trade_pnl
            equity_curve.append(current_equity)

            prev_eq = equity_curve[-2]
            if prev_eq > Decimal("0"):
                ret = (current_equity - prev_eq) / prev_eq
                daily_returns.append(ret)

            trades.append(trade_entry)

        trade_count = len(orders)
        win_rate = Decimal(win_count) / Decimal(trade_count) if trade_count > 0 else Decimal("0")
        avg_win = gross_profit / Decimal(win_count) if win_count > 0 else Decimal("0")
        avg_loss = gross_loss / Decimal(loss_count) if loss_count > 0 else Decimal("0")
        avg_cost = total_costs / Decimal(trade_count) if trade_count > 0 else Decimal("0")

        net_pnl = gross_profit - gross_loss
        expectancy = calculate_expectancy(win_rate, avg_win, avg_loss, avg_cost)
        profit_factor = calculate_profit_factor(gross_profit, gross_loss, total_costs)

        by_regime: dict[str, dict[str, Any]] = {}
        for regime in sorted(regime_buckets):
            bucket = regime_buckets[regime]
            count = bucket["trade_count"]
            b_win_rate = Decimal(bucket["win_count"]) / Decimal(count) if count > 0 else Decimal("0")
            b_avg_win = (
                bucket["gross_profit"] / Decimal(bucket["win_count"])
                if bucket["win_count"] > 0
                else Decimal("0")
            )
            b_avg_loss = (
                bucket["gross_loss"] / Decimal(bucket["loss_count"])
                if bucket["loss_count"] > 0
                else Decimal("0")
            )
            b_avg_cost = bucket["total_costs"] / Decimal(count) if count > 0 else Decimal("0")
            b_net_pnl = bucket["gross_profit"] - bucket["gross_loss"]
            b_expectancy = calculate_expectancy(b_win_rate, b_avg_win, b_avg_loss, b_avg_cost)
            b_profit_factor = calculate_profit_factor(
                bucket["gross_profit"], bucket["gross_loss"], bucket["total_costs"]
            )
            b_max_dd_pct, b_max_dd_amt = calculate_max_drawdown(bucket["equity_curve"])
            b_sharpe = calculate_sharpe_ratio(bucket["returns"])
            b_sortino = calculate_sortino_ratio(bucket["returns"])
            by_regime[regime] = {
                "trade_count": count,
                "win_count": bucket["win_count"],
                "loss_count": bucket["loss_count"],
                "gross_profit": str(bucket["gross_profit"]),
                "gross_loss": str(bucket["gross_loss"]),
                "total_transaction_costs": str(bucket["total_costs"]),
                "net_pnl": str(b_net_pnl),
                "win_rate": str(round(b_win_rate, 4)),
                "avg_win": str(b_avg_win),
                "avg_loss": str(b_avg_loss),
                "expectancy": str(b_expectancy),
                "profit_factor": str(b_profit_factor) if b_profit_factor is not None else None,
                "sharpe_ratio": str(b_sharpe) if b_sharpe is not None else None,
                "sortino_ratio": str(b_sortino) if b_sortino is not None else None,
                "max_drawdown_pct": str(b_max_dd_pct),
                "max_drawdown_amount": str(b_max_dd_amt),
                "trades": bucket["trades"],
            }

        # Observability: surface trades whose originating rule fired with no
        # regime tag so thin regime buckets are visible rather than silent.
        if missing_regime_count > 0:
            logger.info(
                "run_stats_unattributed_regime_trades",
                extra={
                    "run_id": str(run.id),
                    "symbol": run.symbol,
                    "missing_regime_count": missing_regime_count,
                },
            )

        # Per-rule attribution (Batch M4.5): the same metrics recomputed for each
        # rule's own trades, using the existing pure ``calculate_*`` helpers.
        by_rule: dict[str, dict[str, Any]] = {}
        for rule_id in sorted(rule_buckets):
            bucket = rule_buckets[rule_id]
            count = bucket["trade_count"]
            r_win_rate = (
                Decimal(bucket["win_count"]) / Decimal(count) if count > 0 else Decimal("0")
            )
            r_avg_win = (
                bucket["gross_profit"] / Decimal(bucket["win_count"])
                if bucket["win_count"] > 0
                else Decimal("0")
            )
            r_avg_loss = (
                bucket["gross_loss"] / Decimal(bucket["loss_count"])
                if bucket["loss_count"] > 0
                else Decimal("0")
            )
            r_avg_cost = bucket["total_costs"] / Decimal(count) if count > 0 else Decimal("0")
            r_net_pnl = bucket["gross_profit"] - bucket["gross_loss"]
            r_expectancy = calculate_expectancy(r_win_rate, r_avg_win, r_avg_loss, r_avg_cost)
            r_profit_factor = calculate_profit_factor(
                bucket["gross_profit"], bucket["gross_loss"], bucket["total_costs"]
            )
            r_max_dd_pct, r_max_dd_amt = calculate_max_drawdown(bucket["equity_curve"])
            r_sharpe = calculate_sharpe_ratio(bucket["returns"])
            r_sortino = calculate_sortino_ratio(bucket["returns"])
            by_rule[rule_id] = {
                "rule_id": rule_id,
                "trade_count": count,
                "win_count": bucket["win_count"],
                "loss_count": bucket["loss_count"],
                "gross_profit": str(bucket["gross_profit"]),
                "gross_loss": str(bucket["gross_loss"]),
                "total_transaction_costs": str(bucket["total_costs"]),
                "net_pnl": str(r_net_pnl),
                "win_rate": str(round(r_win_rate, 4)),
                "avg_win": str(r_avg_win),
                "avg_loss": str(r_avg_loss),
                "expectancy": str(r_expectancy),
                "profit_factor": str(r_profit_factor) if r_profit_factor is not None else None,
                "sharpe_ratio": str(r_sharpe) if r_sharpe is not None else None,
                "sortino_ratio": str(r_sortino) if r_sortino is not None else None,
                "max_drawdown_pct": str(r_max_dd_pct),
                "max_drawdown_amount": str(r_max_dd_amt),
                "trades": bucket["trades"],
            }

        # Reconciliation: every fill must trace to exactly one rule (or be
        # unattributed), and the totals must match the run's total fill count.
        attributed_trade_count = sum(bucket["trade_count"] for bucket in rule_buckets.values())
        by_rule_fill_groups = group_fills_by_rule(fills, rule_executions, order_by_id)
        if (
            attributed_trade_count + unattributed_trade_count != len(fills)
            or sum(len(group) for group in by_rule_fill_groups.values()) != attributed_trade_count
        ):
            logger.warning(
                "rule_attribution_reconciliation_mismatch",
                extra={
                    "run_id": str(run.id),
                    "attributed_trade_count": attributed_trade_count,
                    "unattributed_trade_count": unattributed_trade_count,
                    "attributed_fill_count": sum(
                        len(group) for group in by_rule_fill_groups.values()
                    ),
                    "total_fill_count": len(fills),
                },
            )

        max_dd_pct, max_dd_amt = calculate_max_drawdown(equity_curve)
        sharpe = calculate_sharpe_ratio(daily_returns)
        sortino = calculate_sortino_ratio(daily_returns)

        snapshots = TASnapshotRepository().find_in_range(
            run.symbol, run.range_start, run.range_end, timeframe=run.timeframe
        )
        if snapshots:
            first_raw = snapshots[0].raw_payload or {}
            last_raw = snapshots[-1].raw_payload or {}
            start_p = BacktestRunnerService._extract_decimal(
                first_raw.get("open") or first_raw.get("close")
            )
            end_p = BacktestRunnerService._extract_decimal(
                last_raw.get("close") or last_raw.get("open")
            )
            benchmark_return = calculate_benchmark_return(start_p, end_p)
        else:
            benchmark_return = None

        # IS/OOS metrics (Batch IS-OOS-METRICS-1): the full metrics suite
        # computed independently for the in-sample and out-of-sample halves of
        # the static split, mirroring the by_regime/by_rule bucket pattern. An
        # empty half yields None for ratio-based metrics (profit_factor, sharpe,
        # sortino) exactly like a by_regime bucket with too few trades.
        split_metrics: dict[str, dict[str, Any]] = {}
        for split_name, bucket in (("in_sample", is_bucket), ("out_of_sample", oos_bucket)):
            count = bucket["trade_count"]
            s_win_rate = (
                Decimal(bucket["win_count"]) / Decimal(count) if count > 0 else Decimal("0")
            )
            s_avg_win = (
                bucket["gross_profit"] / Decimal(bucket["win_count"])
                if bucket["win_count"] > 0
                else Decimal("0")
            )
            s_avg_loss = (
                bucket["gross_loss"] / Decimal(bucket["loss_count"])
                if bucket["loss_count"] > 0
                else Decimal("0")
            )
            s_avg_cost = bucket["total_costs"] / Decimal(count) if count > 0 else Decimal("0")
            s_net_pnl = bucket["gross_profit"] - bucket["gross_loss"]
            s_expectancy = calculate_expectancy(s_win_rate, s_avg_win, s_avg_loss, s_avg_cost)
            s_profit_factor = calculate_profit_factor(
                bucket["gross_profit"], bucket["gross_loss"], bucket["total_costs"]
            )
            s_max_dd_pct, s_max_dd_amt = calculate_max_drawdown(bucket["equity_curve"])
            s_sharpe = calculate_sharpe_ratio(bucket["returns"])
            s_sortino = calculate_sortino_ratio(bucket["returns"])
            split_metrics[split_name] = {
                "trade_count": count,
                "win_count": bucket["win_count"],
                "loss_count": bucket["loss_count"],
                "gross_profit": str(bucket["gross_profit"]),
                "gross_loss": str(bucket["gross_loss"]),
                "total_transaction_costs": str(bucket["total_costs"]),
                "net_pnl": str(s_net_pnl),
                "win_rate": str(round(s_win_rate, 4)),
                "avg_win": str(s_avg_win),
                "avg_loss": str(s_avg_loss),
                "expectancy": str(s_expectancy),
                "profit_factor": str(s_profit_factor) if s_profit_factor is not None else None,
                "sharpe_ratio": str(s_sharpe) if s_sharpe is not None else None,
                "sortino_ratio": str(s_sortino) if s_sortino is not None else None,
                "max_drawdown_pct": str(s_max_dd_pct),
                "max_drawdown_amount": str(s_max_dd_amt),
                "trades": bucket["trades"],
            }

        run.net_pnl = net_pnl
        run.expectancy = expectancy
        run.profit_factor = profit_factor
        run.max_drawdown = max_dd_pct
        run.sharpe_ratio = sharpe
        run.sortino_ratio = sortino
        run.benchmark_return = benchmark_return
        run.risk_rejected_count = risk_rejected_count
        run.save()

        return {
            "status": run.status,
            "trade_count": trade_count,
            "fill_count": len(fills),
            "win_count": win_count,
            "loss_count": loss_count,
            "risk_rejected_count": risk_rejected_count,
            "gross_profit": str(gross_profit),
            "gross_loss": str(gross_loss),
            "total_transaction_costs": str(total_costs),
            "total_slippage_impact": str(total_slippage),
            "net_pnl": str(net_pnl),
            "win_rate": str(round(win_rate, 4)),
            "expectancy": str(expectancy),
            "profit_factor": str(profit_factor) if profit_factor is not None else None,
            "max_drawdown_pct": str(max_dd_pct),
            "sharpe_ratio": str(sharpe) if sharpe is not None else None,
            "sortino_ratio": str(sortino) if sortino is not None else None,
            "benchmark_return_pct": str(benchmark_return) if benchmark_return is not None else None,
            "equity_at_completion": str(capital.equity) if capital else "0",
            "available_capital": str(capital.available_capital) if capital else "0",
            "in_sample": split_metrics["in_sample"],
            "out_of_sample": split_metrics["out_of_sample"],
            "by_regime": by_regime,
            "missing_regime_count": missing_regime_count,
            "by_rule": by_rule,
            "unattributed_trade_count": unattributed_trade_count,
            "trades": trades,
        }

    def _nse_cost_for_order(self, order: Any, model: Any, compute_trade_cost: Any) -> Decimal:
        """Full NSE cost (incl. impact) for one order's leg."""
        price = order.avg_fill_price or order.entry_price or Decimal("0")
        return compute_trade_cost(
            quantity=order.filled_quantity,
            price=price,
            side=order.side,
            model=model,
        )["total"]

    def _nse_impact_for_order(self, order: Any, model: Any, compute_trade_cost: Any) -> Decimal:
        """Size-dependent impact leg only (the NSE analogue of slippage)."""
        price = order.avg_fill_price or order.entry_price or Decimal("0")
        return compute_trade_cost(
            quantity=order.filled_quantity,
            price=price,
            side=order.side,
            model=model,
        )["impact_cost"]

    def _resolve_regimes(self, orders: list[Any]) -> dict[uuid.UUID, str]:
        """Map each order's correlation_id to its market regime.

        An ``Order`` carries the same ``correlation_id`` as the ``PacketBuilt``
        event that produced its triggering rule firing, and that id is stored as
        ``RuleExecution.analysis_event_id``. We read the ``regime`` key injected
        into ``trigger_data`` at rule-firing time. One query per run.
        """
        from apps.rule_engine.infrastructure.models import RuleExecution

        correlation_ids = {o.correlation_id for o in orders if o.correlation_id}
        regime_map: dict[uuid.UUID, str] = {}
        if not correlation_ids:
            return regime_map
        rows = RuleExecution.objects.filter(
            analysis_event_id__in=correlation_ids
        ).only("analysis_event_id", "trigger_data")
        for row in rows:
            regime = (row.trigger_data or {}).get("regime")
            if regime and row.analysis_event_id not in regime_map:
                regime_map[row.analysis_event_id] = regime
        return regime_map
