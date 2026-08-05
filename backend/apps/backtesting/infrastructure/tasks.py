"""Batch M3 — Celery entry point for backtest replay.

Backtests run on the ``analytics`` queue but MUST execute synchronously:
the simulation contextvars (clock + backtest account) only propagate within
the calling process, so ``CELERY_TASK_ALWAYS_EAGER`` is a hard requirement
for a backtest run (see ``BacktestRunnerService``).
"""

from __future__ import annotations

import uuid

from celery import shared_task

from apps.backtesting.services import BacktestRunnerService
from core.tasks.base import DEFAULT_MAX_RETRIES, DEFAULT_RETRY_DELAY, BaseTask


@shared_task(
    name="tradevision.backtesting.run_backtest",
    queue="analytics",
    bind=True,
    base=BaseTask,
    max_retries=DEFAULT_MAX_RETRIES,
    default_retry_delay=DEFAULT_RETRY_DELAY,
)
def run_backtest(self, run_id: str) -> dict[str, str]:
    """Execute a ``BacktestRun`` through the real event-driven pipeline.

    Idempotent at the run level: a COMPLETED run is a no-op and a FAILED run
    resumes from its cursor, so redelivery never re-processes consumed bars.
    """
    return BacktestRunnerService().run(uuid.UUID(run_id))
