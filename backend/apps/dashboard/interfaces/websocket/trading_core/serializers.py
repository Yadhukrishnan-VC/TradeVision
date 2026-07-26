from __future__ import annotations

from rest_framework import serializers


class WebSocketPositionSnapshotSerializer(serializers.Serializer):
    position_id = serializers.UUIDField()
    account_id = serializers.UUIDField()
    symbol = serializers.CharField()
    side = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=20, decimal_places=8)
    entry_price = serializers.DecimalField(max_digits=20, decimal_places=8)
    current_price = serializers.DecimalField(max_digits=20, decimal_places=8, allow_null=True)
    unrealized_pnl = serializers.DecimalField(max_digits=20, decimal_places=8, allow_null=True)
    is_open = serializers.BooleanField()
    opened_at = serializers.DateTimeField(allow_null=True)


class WebSocketOrderSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    account_id = serializers.UUIDField()
    symbol = serializers.CharField()
    side = serializers.CharField()
    status = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=20, decimal_places=8)
    filled_quantity = serializers.DecimalField(max_digits=20, decimal_places=8)
    placed_at = serializers.DateTimeField(allow_null=True)


class WebSocketCompositionSerializer(serializers.Serializer):
    account_id = serializers.UUIDField()
    holdings = serializers.ListField(child=serializers.DictField(), allow_empty=True)
    total_market_value = serializers.DecimalField(max_digits=20, decimal_places=8)
