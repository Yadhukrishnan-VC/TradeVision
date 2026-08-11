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
from decimal import Decimal
from typing import Any

from django.conf import settings

from apps.backtesting.domain.metrics import (
    calculate_benchmark_return,
    calculate_expectancy,
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
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

                # Execute any pending orders from prior bars at THIS bar's open price
                raw = snapshot.raw_payload or {}
                bar_open = self._extract_decimal(raw.get("open") or raw.get("close"))
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

        gross_profit = Decimal("0")
        gross_loss = Decimal("0")
        total_costs = Decimal("0")
        total_slippage = Decimal("0")
        win_count = 0
        loss_count = 0

        comm_rate = Decimal(str(run.commission_rate or "0"))
        slip_bps = Decimal(str(run.slippage_bps or "0"))

        for fill in fills:
            fee = fill.quantity * fill.price * comm_rate
            slip_impact = fill.quantity * fill.price * (slip_bps / Decimal("10000"))
            total_costs += fee + slip_impact
            total_slippage += slip_impact

        trades: list[dict[str, Any]] = []
        initial_eq = capital.equity if capital else Decimal("100000.00")
        equity_curve: list[Decimal] = [initial_eq]
        daily_returns: list[Decimal] = []

        current_equity = initial_eq

        for order in orders:
            direction = Decimal("1") if str(order.side).upper() == "LONG" else Decimal("-1")
            avg_fill = order.avg_fill_price or Decimal("0")
            raw_pnl = (avg_fill - order.entry_price) * order.filled_quantity * direction

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

            current_equity += net_trade_pnl
            equity_curve.append(current_equity)

            prev_eq = equity_curve[-2]
            if prev_eq > Decimal("0"):
                ret = (current_equity - prev_eq) / prev_eq
                daily_returns.append(ret)

            trades.append(
                {
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
            )

        trade_count = len(orders)
        win_rate = Decimal(win_count) / Decimal(trade_count) if trade_count > 0 else Decimal("0")
        avg_win = gross_profit / Decimal(win_count) if win_count > 0 else Decimal("0")
        avg_loss = gross_loss / Decimal(loss_count) if loss_count > 0 else Decimal("0")
        avg_cost = total_costs / Decimal(trade_count) if trade_count > 0 else Decimal("0")

        net_pnl = gross_profit - gross_loss
        expectancy = calculate_expectancy(win_rate, avg_win, avg_loss, avg_cost)
        profit_factor = calculate_profit_factor(gross_profit, gross_loss, total_costs)
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

        total_seconds = (run.range_end - run.range_start).total_seconds()
        split_seconds = total_seconds * float(run.in_sample_ratio)
        split_ts = run.range_start.timestamp() + split_seconds

        is_trades = []
        oos_trades = []
        for order_dict, order_obj in zip(trades, orders):
            if order_obj.created_at and order_obj.created_at.timestamp() <= split_ts:
                is_trades.append(order_dict)
            else:
                oos_trades.append(order_dict)

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
            "in_sample": {"trade_count": len(is_trades), "trades": is_trades},
            "out_of_sample": {"trade_count": len(oos_trades), "trades": oos_trades},
            "trades": trades,
        }
