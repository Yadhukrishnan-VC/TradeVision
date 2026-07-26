from __future__ import annotations

from rest_framework import serializers

from apps.dashboard.application.trading_core.dto import (
    DashboardHomeSummaryDTO,
    HoldingDTO,
    OrderSnapshotDTO,
    PortfolioCompositionDTO,
    PositionSnapshotDTO,
    TradeRecordDTO,
)


class DashboardHomeSummarySerializer(serializers.Serializer):
    account_id = serializers.UUIDField()
    open_positions_count = serializers.IntegerField()
    open_orders_count = serializers.IntegerField()
    today_realized_pnl = serializers.DecimalField(max_digits=20, decimal_places=8)
    today_unrealized_pnl = serializers.DecimalField(max_digits=20, decimal_places=8)
    active_alerts_count = serializers.IntegerField()
    broker_connection_status = serializers.CharField()
    market_session_status = serializers.CharField()
    last_updated_at = serializers.DateTimeField(allow_null=True)

    class Meta:
        fields = [
            "account_id", "open_positions_count", "open_orders_count",
            "today_realized_pnl", "today_unrealized_pnl", "active_alerts_count",
            "broker_connection_status", "market_session_status", "last_updated_at",
        ]


class HoldingSerializer(serializers.Serializer):
    account_id = serializers.UUIDField()
    symbol = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=20, decimal_places=8)
    avg_cost = serializers.DecimalField(max_digits=20, decimal_places=8)
    cost_basis = serializers.DecimalField(max_digits=20, decimal_places=8)
    market_value = serializers.DecimalField(max_digits=20, decimal_places=8, allow_null=True)
    allocation_pct = serializers.DecimalField(max_digits=10, decimal_places=4, allow_null=True)
    unrealized_pnl = serializers.DecimalField(max_digits=20, decimal_places=8, allow_null=True)
    opened_at = serializers.DateTimeField(allow_null=True)


class PortfolioCompositionSerializer(serializers.Serializer):
    account_id = serializers.UUIDField()
    holdings = HoldingSerializer(many=True)
    total_market_value = serializers.DecimalField(max_digits=20, decimal_places=8)
    total_cost_basis = serializers.DecimalField(max_digits=20, decimal_places=8)
    cash_balance = serializers.DecimalField(max_digits=20, decimal_places=8)


class PositionSnapshotSerializer(serializers.Serializer):
    position_id = serializers.UUIDField()
    account_id = serializers.UUIDField()
    symbol = serializers.CharField()
    side = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=20, decimal_places=8)
    entry_price = serializers.DecimalField(max_digits=20, decimal_places=8)
    current_price = serializers.DecimalField(max_digits=20, decimal_places=8, allow_null=True)
    unrealized_pnl = serializers.DecimalField(max_digits=20, decimal_places=8, allow_null=True)
    unrealized_pnl_pct = serializers.DecimalField(max_digits=10, decimal_places=4, allow_null=True)
    is_open = serializers.BooleanField()
    opened_at = serializers.DateTimeField(allow_null=True)
    closed_at = serializers.DateTimeField(allow_null=True)


class OrderSnapshotSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    account_id = serializers.UUIDField()
    symbol = serializers.CharField()
    side = serializers.CharField()
    order_type = serializers.CharField()
    status = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=20, decimal_places=8)
    filled_quantity = serializers.DecimalField(max_digits=20, decimal_places=8)
    avg_fill_price = serializers.DecimalField(max_digits=20, decimal_places=8, allow_null=True)
    limit_price = serializers.DecimalField(max_digits=20, decimal_places=8, allow_null=True)
    placed_at = serializers.DateTimeField(allow_null=True)


class TradeRecordSerializer(serializers.Serializer):
    trade_id = serializers.UUIDField()
    account_id = serializers.UUIDField()
    symbol = serializers.CharField()
    side = serializers.CharField()
    entry_price = serializers.DecimalField(max_digits=20, decimal_places=8)
    exit_price = serializers.DecimalField(max_digits=20, decimal_places=8)
    quantity = serializers.DecimalField(max_digits=20, decimal_places=8)
    realized_pnl = serializers.DecimalField(max_digits=20, decimal_places=8)
    realized_pnl_pct = serializers.DecimalField(max_digits=10, decimal_places=4)
    opened_at = serializers.DateTimeField(allow_null=True)
    closed_at = serializers.DateTimeField(allow_null=True)
    holding_period_seconds = serializers.IntegerField()


class ExportRequestSerializer(serializers.Serializer):
    format = serializers.ChoiceField(choices=["csv", "pdf"])
    symbol = serializers.CharField(required=False, allow_null=True)
    side = serializers.CharField(required=False, allow_null=True)
    date_from = serializers.DateTimeField(required=False, allow_null=True)
    date_to = serializers.DateTimeField(required=False, allow_null=True)
    min_pnl = serializers.DecimalField(max_digits=20, decimal_places=8, required=False, allow_null=True)
    max_pnl = serializers.DecimalField(max_digits=20, decimal_places=8, required=False, allow_null=True)


class ExportJobSerializer(serializers.Serializer):
    export_id = serializers.UUIDField()
    status = serializers.CharField()
    format = serializers.CharField()
    file_url = serializers.URLField(allow_null=True)
    requested_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)
    error_message = serializers.CharField(allow_null=True)
