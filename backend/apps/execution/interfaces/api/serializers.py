from __future__ import annotations

from rest_framework import serializers

from apps.execution.infrastructure.models import ExecutionRequest, Fill, Order


class ExecutionRequestSerializer(serializers.ModelSerializer):
    order_id = serializers.UUIDField(source="order.id", read_only=True, allow_null=True)

    class Meta:
        model = ExecutionRequest
        fields = [
            "id",
            "idempotency_key",
            "account_id",
            "symbol",
            "side",
            "quantity",
            "entry_price",
            "stop_loss",
            "correlation_id",
            "causation_id",
            "risk_approved_event_id",
            "rule_id",
            "event_type",
            "status",
            "reason_message",
            "order_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    fills = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "execution_request",
            "account_id",
            "symbol",
            "side",
            "order_type",
            "quantity",
            "status",
            "filled_quantity",
            "avg_fill_price",
            "limit_price",
            "broker_order_ref",
            "broker_name",
            "entry_price",
            "stop_loss",
            "correlation_id",
            "causation_id",
            "fills",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_fills(self, obj: Order) -> list[dict]:
        rows = Fill.objects.filter(order_id=obj.id).order_by("sequence")
        return [
            {
                "id": str(f.id),
                "sequence": f.sequence,
                "quantity": str(f.quantity),
                "price": str(f.price),
                "occurred_at": f.occurred_at,
            }
            for f in rows
        ]
