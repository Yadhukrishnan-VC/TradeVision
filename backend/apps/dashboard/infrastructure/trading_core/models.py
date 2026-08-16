from __future__ import annotations

from django.db import models

from apps.dashboard.infrastructure.common.projection_mixin import ProjectionMetadataMixin


class PositionSnapshot(ProjectionMetadataMixin, models.Model):
    position_id = models.UUIDField(primary_key=True)
    account_id = models.UUIDField(db_index=True)
    symbol = models.CharField(max_length=20)
    side = models.CharField(max_length=4)
    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    entry_price = models.DecimalField(max_digits=20, decimal_places=8)
    is_open = models.BooleanField(default=True)
    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dashboard_positionsnapshot"
        indexes = [
            models.Index(fields=["account_id", "is_open"], name="idx_positions_account_open"),
            models.Index(fields=["account_id", "symbol"]),
        ]

    def __str__(self) -> str:
        return f"PositionSnapshot({self.position_id}, {self.symbol})"


class OrderSnapshot(ProjectionMetadataMixin, models.Model):
    order_id = models.UUIDField(primary_key=True)
    account_id = models.UUIDField(db_index=True)
    symbol = models.CharField(max_length=20)
    side = models.CharField(max_length=4)
    order_type = models.CharField(max_length=10)
    status = models.CharField(max_length=20)
    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    filled_quantity = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    avg_fill_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    limit_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    placed_at = models.DateTimeField()

    class Meta:
        db_table = "dashboard_ordersnapshot"
        indexes = [
            models.Index(fields=["account_id", "status", "placed_at"], name="idx_orders_acct_status_placed"),
            models.Index(fields=["account_id", "symbol", "placed_at"]),
        ]

    def __str__(self) -> str:
        return f"OrderSnapshot({self.order_id}, {self.symbol}, {self.status})"


class TradeRecord(ProjectionMetadataMixin, models.Model):
    trade_id = models.UUIDField(primary_key=True)
    account_id = models.UUIDField(db_index=True)
    symbol = models.CharField(max_length=20)
    side = models.CharField(max_length=4)
    entry_price = models.DecimalField(max_digits=20, decimal_places=8)
    exit_price = models.DecimalField(max_digits=20, decimal_places=8)
    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    realized_pnl = models.DecimalField(max_digits=20, decimal_places=8)
    realized_pnl_pct = models.DecimalField(max_digits=10, decimal_places=4)
    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField()
    holding_period_seconds = models.IntegerField()

    class Meta:
        db_table = "dashboard_traderecord"
        constraints = [
            models.UniqueConstraint(
                fields=["last_event_id"],
                name="uq_traderecord_last_event_id",
            ),
        ]
        indexes = [
            models.Index(fields=["account_id", "closed_at"], name="idx_trades_account_closed"),
            models.Index(fields=["account_id", "symbol", "closed_at"]),
            models.Index(fields=["account_id", "realized_pnl"]),
        ]

    def __str__(self) -> str:
        return f"TradeRecord({self.trade_id}, {self.symbol}, {self.realized_pnl})"


class Holding(ProjectionMetadataMixin, models.Model):
    id = models.UUIDField(primary_key=True)
    account_id = models.UUIDField(db_index=True)
    symbol = models.CharField(max_length=20)
    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    avg_cost = models.DecimalField(max_digits=20, decimal_places=8)
    cost_basis = models.DecimalField(max_digits=20, decimal_places=8)
    opened_at = models.DateTimeField()

    class Meta:
        db_table = "dashboard_holding"
        constraints = [
            models.UniqueConstraint(
                fields=["account_id", "symbol"],
                name="uq_holding_account_symbol",
            ),
        ]
        indexes = [
            models.Index(fields=["account_id", "quantity"], name="idx_holding_account_qty"),
        ]

    def __str__(self) -> str:
        return f"Holding({self.account_id}, {self.symbol}, {self.quantity})"


class DashboardHomeSummary(ProjectionMetadataMixin, models.Model):
    account_id = models.UUIDField(primary_key=True)
    open_positions_count = models.IntegerField(default=0)
    open_orders_count = models.IntegerField(default=0)
    today_realized_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    today_unrealized_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    active_alerts_count = models.IntegerField(default=0)
    broker_connection_status = models.CharField(max_length=20, default="disconnected")
    market_session_status = models.CharField(max_length=20, default="closed")

    class Meta:
        db_table = "dashboard_homesummary"

    def __str__(self) -> str:
        return f"DashboardHomeSummary({self.account_id})"


class ExportJob(models.Model):
    export_id = models.UUIDField(primary_key=True)
    account_id = models.UUIDField(db_index=True)
    status = models.CharField(max_length=20, default="pending")
    format = models.CharField(max_length=10)
    file_url = models.URLField(null=True, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "dashboard_exportjob"
        indexes = [
            models.Index(fields=["account_id", "status"]),
        ]

    def __str__(self) -> str:
        return f"ExportJob({self.export_id}, {self.status})"
