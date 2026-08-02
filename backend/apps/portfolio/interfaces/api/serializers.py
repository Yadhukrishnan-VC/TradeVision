from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers


def _fmt(value: Decimal) -> str:
    """Render a Decimal in its natural form (no trailing zeroes)."""
    return format(value.normalize(), "f")


class AccountCapitalSerializer(serializers.Serializer):
    """Serializes the authoritative capital snapshot (ADR-028 §2.2)."""

    def to_representation(self, instance) -> dict:
        return {
            "account_id": str(instance.account_id),
            "cash": _fmt(instance.cash),
            "margin_used": _fmt(instance.margin_used),
            "equity": _fmt(instance.equity),
            "available_capital": _fmt(instance.available_capital),
            "realized_pnl_today": _fmt(instance.realized_pnl_today),
            "unrealized_pnl_today": _fmt(instance.unrealized_pnl_today),
        }


class PositionSerializer(serializers.Serializer):
    """Serializes an open position with live mark-to-market fields.

    Input is the dict built by the view from the domain entity plus the
    query service's live current-price / unrealized / exposure values.
    """

    def to_representation(self, instance: dict) -> dict:
        quantity: Decimal = instance["quantity"]
        current_price = instance["current_price"]
        return {
            "account_id": str(instance["account_id"]),
            "symbol": instance["symbol"],
            "side": instance["side"].value
            if hasattr(instance["side"], "value")
            else instance["side"],
            "quantity": _fmt(quantity),
            "avg_entry_price": _fmt(instance["avg_entry_price"]),
            "opened_at": instance["opened_at"].isoformat(),
            "current_price": (
                _fmt(current_price) if current_price is not None else None
            ),
            "unrealized_pnl": _fmt(instance["unrealized_pnl"]),
            "exposure": _fmt(instance["exposure"]),
        }


class FillRequestSerializer(serializers.Serializer):
    """Request body for the manual/paper fill-recording endpoint.

    Gated by the already-existing ``Scope.MANAGE_EXECUTION`` (ADR-028 §2.5) —
    this is the honest placeholder for a future broker-sync adapter, never
    assumed to be a live execution path.
    """

    account_id = serializers.UUIDField(required=False)
    symbol = serializers.CharField(max_length=50)
    side = serializers.ChoiceField(choices=["LONG", "SHORT"])
    quantity = serializers.DecimalField(max_digits=20, decimal_places=8)
    price = serializers.DecimalField(max_digits=20, decimal_places=8)
    source_fill_id = serializers.UUIDField(required=False)
    occurred_at = serializers.DateTimeField(required=False)

    def validate_quantity(self, value: Decimal) -> Decimal:
        if value <= 0:
            raise serializers.ValidationError("quantity must be positive")
        return value

    def validate_price(self, value: Decimal) -> Decimal:
        if value <= 0:
            raise serializers.ValidationError("price must be positive")
        return value
