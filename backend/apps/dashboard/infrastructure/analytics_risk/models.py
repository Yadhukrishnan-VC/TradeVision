from __future__ import annotations

from uuid import uuid4

from django.db import models


class PnLSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    account_id = models.UUIDField(db_index=True)
    snapshot_at = models.DateTimeField()
    realized_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    unrealized_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    total_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    cumulative_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    peak_cumulative_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    drawdown_pct = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    last_event_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "dashboard_pnl_snapshot"
        indexes = [
            models.Index(fields=["account_id", "-snapshot_at"]),
        ]

    def __str__(self) -> str:
        return f"PnLSnapshot({self.account_id}, {self.snapshot_at})"


class PnLDailyRollup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    account_id = models.UUIDField(db_index=True)
    trading_date = models.DateField()
    realized_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    unrealized_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    total_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    cumulative_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    peak_cumulative_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    drawdown_pct = models.DecimalField(max_digits=10, decimal_places=4, default=0)

    class Meta:
        db_table = "dashboard_pnl_daily_rollup"
        constraints = [
            models.UniqueConstraint(
                fields=["account_id", "trading_date"],
                name="uq_pnl_daily_account_date",
            ),
        ]

    def __str__(self) -> str:
        return f"PnLDailyRollup({self.account_id}, {self.trading_date})"


class PerformanceSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    account_id = models.UUIDField(db_index=True)
    period = models.CharField(max_length=10)
    computed_at = models.DateTimeField(auto_now=True)
    win_rate = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    avg_win = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    avg_loss = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    profit_factor = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    expectancy = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    sharpe_like_ratio = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    total_trades = models.IntegerField(default=0)
    winning_trades = models.IntegerField(default=0)
    losing_trades = models.IntegerField(default=0)

    class Meta:
        db_table = "dashboard_performance_snapshot"
        constraints = [
            models.UniqueConstraint(
                fields=["account_id", "period"],
                name="uq_performance_account_period",
            ),
        ]

    def __str__(self) -> str:
        return f"PerformanceSnapshot({self.account_id}, {self.period})"


class RiskMetricSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    account_id = models.UUIDField(db_index=True)
    snapshot_at = models.DateTimeField()
    total_exposure = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    largest_position_pct = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    sector_concentration_pct = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    leverage_ratio = models.DecimalField(max_digits=10, decimal_places=4, default=0)

    class Meta:
        db_table = "dashboard_risk_metric_snapshot"
        indexes = [
            models.Index(fields=["account_id", "-snapshot_at"]),
        ]

    def __str__(self) -> str:
        return f"RiskMetricSnapshot({self.account_id}, {self.snapshot_at})"


class RiskAlertProjection(models.Model):
    alert_id = models.UUIDField(primary_key=True, default=uuid4)
    account_id = models.UUIDField(db_index=True)
    alert_type = models.CharField(max_length=50)
    severity = models.CharField(max_length=20)
    message = models.TextField()
    raised_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    last_event_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "dashboard_risk_alert_projection"
        indexes = [
            models.Index(fields=["account_id", "-raised_at"]),
        ]

    def __str__(self) -> str:
        return f"RiskAlertProjection({self.alert_id}, {self.alert_type})"
