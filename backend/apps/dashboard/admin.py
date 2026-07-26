from __future__ import annotations

from django.contrib import admin

from apps.dashboard.infrastructure.trading_core.models import (
    DashboardHomeSummary,
    Holding,
    OrderSnapshot,
    PositionSnapshot,
    TradeRecord,
)


@admin.register(DashboardHomeSummary)
class DashboardHomeSummaryAdmin(admin.ModelAdmin):
    list_display = [
        "account_id", "open_positions_count", "open_orders_count",
        "today_realized_pnl", "broker_connection_status", "projection_updated_at",
    ]
    search_fields = ["account_id"]
    readonly_fields = ["account_id", "projection_version", "projection_updated_at"]


@admin.register(Holding)
class HoldingAdmin(admin.ModelAdmin):
    list_display = ["account_id", "symbol", "quantity", "avg_cost", "cost_basis", "opened_at"]
    search_fields = ["account_id", "symbol"]
    list_filter = ["symbol"]
    readonly_fields = ["projection_version", "projection_updated_at"]


@admin.register(PositionSnapshot)
class PositionSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        "position_id", "account_id", "symbol", "side",
        "quantity", "entry_price", "is_open", "opened_at",
    ]
    search_fields = ["account_id", "symbol", "position_id"]
    list_filter = ["is_open", "side", "symbol"]
    readonly_fields = ["projection_version", "projection_updated_at"]


@admin.register(OrderSnapshot)
class OrderSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        "order_id", "account_id", "symbol", "side",
        "status", "quantity", "filled_quantity", "placed_at",
    ]
    search_fields = ["account_id", "symbol", "order_id"]
    list_filter = ["status", "side", "symbol"]
    readonly_fields = ["projection_version", "projection_updated_at"]


@admin.register(TradeRecord)
class TradeRecordAdmin(admin.ModelAdmin):
    list_display = [
        "trade_id", "account_id", "symbol", "side",
        "quantity", "realized_pnl", "opened_at", "closed_at",
    ]
    search_fields = ["account_id", "symbol", "trade_id"]
    list_filter = ["side", "symbol"]
    readonly_fields = ["projection_version", "projection_updated_at"]
