"""Batch M3 — Backtest runner and read-only run statistics.

The runner replays historical ``TASnapshot`` payloads through the *real*
event-driven pipeline (``TechnicalAnalysisIngestionService`` -> EventBus ->
intelligence -> rule_engine -> risk_management -> execution -> PaperBroker)
one bar at a time. For each bar it:

* derives a deterministic correlation id from ``(run_id, snapshot_id)`` via
  ``IdempotencyKey.generate``,
* binds the backtest account id and the snapshot's historical timestamp via
  the ContextVar-based simulation clock,
* ingests the raw payload with the production ingestion service UNCHANGED.

No rule, risk, or execution logic is duplicated or modified here — this
service only replays historical payloads and drives the cursor.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from django.conf import settings

from apps.backtesting.models import BacktestRun, BacktestRunStatus
from apps.backtesting.repository import BacktestRunRepository
from apps.common.domain.value_objects import IdempotencyKey
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.technical_analysis.application.services import TechnicalAnalysisIngestionService
from apps.technical_analysis.infrastructure.repositories import TASnapshotRepository
from core.clock import bind_simulated_time, get_clock
from core.execution_context import bind_account_override
from core.services import BaseService

logger = logging.getLogger(__name__)


def _correlation_id_for(run_id: uuid.UUID, snapshot_id: uuid.UUID) -> uuid.UUID:
    """Deterministic, traceable correlation id for one historical bar.

    Same ``(run_id, snapshot_id)`` always yields the same UUID, so a resumed
    run keeps every record traceable to the exact bar that produced it.
    """
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
            for snapshot in pending:
                correlation_id = _correlation_id_for(run.id, snapshot.id)
                with bind_account_override(run.account_id), bind_simulated_time(
                    snapshot.snapshot_timestamp
                ):
                    self._ingest(snapshot.raw_payload, correlation_id)
                self._runs.update_cursor(run_id, snapshot.id)
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
            # Partial Order/Fill rows are intentionally preserved; the cursor
            # makes a resumed run resume from the next bar.
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


class BacktestStatsService(BaseService):
    """Read-only aggregation of a run's records, scoped by its account.

    No P&L is invented: per-trade realized P&L is the signed price difference
    reusing the existing ``avg_fill_price`` / ``entry_price`` / ``quantity``
    fields, and equity/capital come straight from ``AccountCapitalState``.
    """

    def run_stats(self, run: BacktestRun) -> dict[str, Any]:
        from decimal import Decimal

        from apps.execution.infrastructure.models import Fill, Order
        from apps.portfolio.infrastructure.models import AccountCapitalState

        orders = list(
            Order.objects.filter(account_id=run.account_id).order_by("created_at")
        )
        fills = list(
            Fill.objects.filter(order__account_id=run.account_id).order_by("created_at")
        )
        capital = AccountCapitalState.objects.filter(account_id=run.account_id).first()

        trades: list[dict[str, Any]] = []
        win_count = 0
        loss_count = 0
        for order in orders:
            direction = 1 if str(order.side).upper() == "LONG" else -1
            avg_fill = order.avg_fill_price or Decimal(0)
            realized = (
                (avg_fill - order.entry_price) * order.filled_quantity * direction
            )
            if realized > 0:
                win_count += 1
            elif realized < 0:
                loss_count += 1
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
                    "realized_pnl": str(realized),
                }
            )

        return {
            "status": run.status,
            "trade_count": len(orders),
            "fill_count": len(fills),
            "win_count": win_count,
            "loss_count": loss_count,
            "equity_at_completion": str(capital.equity) if capital else "0",
            "available_capital": str(capital.available_capital) if capital else "0",
            "realized_pnl": str(capital.realized_pnl_today) if capital else "0",
            "trades": trades,
        }
