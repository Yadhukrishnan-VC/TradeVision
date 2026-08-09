"""Batch M3 — Historical Replay & Backtesting.

``BacktestRun`` records one historical replay: a symbol/timeframe/date-range
and the isolated account it replays into. The runner consumes historical
``TASnapshot`` payloads in chronological order through the real event-driven
pipeline while an injected simulation clock freezes evaluation time.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import models

from core.models import BaseModel


class BacktestRunStatus(models.TextChoices):
    """Lifecycle of a backtest run: PENDING -> RUNNING -> COMPLETED (or FAILED)."""

    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


class BacktestRun(BaseModel):
    """One historical replay run bound to a dedicated, isolated account.

    The run is the idempotency boundary of a backtest: the runner derives a
    deterministic ``correlation_id`` from ``(run_id, snapshot_id)`` and
    advances ``last_processed_snapshot_id`` as snapshots are consumed, so a
    COMPLETED run is a no-op and a FAILED run resumes from its cursor without
    re-processing bars that already produced records.
    """

    symbol = models.CharField(max_length=100, db_index=True)
    timeframe = models.CharField(max_length=20, blank=True, default="")
    range_start = models.DateTimeField()
    range_end = models.DateTimeField()
    account = models.OneToOneField(
        "accounts.Account",
        on_delete=models.CASCADE,
        related_name="backtest_run",
        help_text="Dedicated, isolated account that owns every record of this run.",
    )
    status = models.CharField(
        max_length=20,
        choices=BacktestRunStatus.choices,
        default=BacktestRunStatus.PENDING,
        db_index=True,
    )
    commission_rate = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=Decimal("0.0003"),
        help_text="Brokerage/commission rate as a decimal (e.g. 0.0003 for 30 bps).",
    )
    slippage_bps = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal("5.0"),
        help_text="Execution slippage in basis points (e.g. 5.0 for 5 bps).",
    )
    in_sample_ratio = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.70"),
        help_text="Fraction of date range reserved for In-Sample training/observation.",
    )
    net_pnl = models.DecimalField(
        max_digits=20, decimal_places=4, null=True, blank=True
    )
    expectancy = models.DecimalField(
        max_digits=20, decimal_places=4, null=True, blank=True
    )
    profit_factor = models.DecimalField(
        max_digits=20, decimal_places=4, null=True, blank=True
    )
    max_drawdown = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    sharpe_ratio = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    sortino_ratio = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    benchmark_return = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    risk_rejected_count = models.IntegerField(default=0)
    last_processed_snapshot_id = models.UUIDField(null=True, blank=True)
    failure_reason = models.TextField(default="", blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "backtesting_backtestrun"
        verbose_name = "Backtest Run"
        verbose_name_plural = "Backtest Runs"
        indexes = [
            models.Index(fields=["symbol", "range_start", "range_end"], name="idx_bt_symbol_range"),
            models.Index(fields=["status"], name="idx_bt_status"),
        ]

    def __str__(self) -> str:
        return (
            f"BacktestRun({self.status}/{self.symbol}/{self.timeframe}/"
            f"{self.range_start:%Y-%m-%d}->{self.range_end:%Y-%m-%d})"
        )
