from __future__ import annotations

from decimal import Decimal
from typing import Any

from rest_framework import serializers


def _fmt(value: Decimal) -> str:
    """Render a Decimal in its natural form (no trailing zeroes)."""
    return format(value.normalize(), "f")


class WatchlistAddSerializer(serializers.Serializer):
    """Request body for adding an instrument to an account's watchlist."""

    account_id = serializers.UUIDField()
    instrument_token = serializers.IntegerField()
    note = serializers.CharField(
        max_length=280,
        required=False,
        allow_blank=True,
        default="",
    )


class WatchlistReorderSerializer(serializers.Serializer):
    """Request body for applying a new display order to a watchlist."""

    account_id = serializers.UUIDField()
    instrument_tokens = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
    )

    def validate_instrument_tokens(self, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise serializers.ValidationError("instrument_tokens must not contain duplicates")
        return value


class WatchlistEntrySerializer(serializers.Serializer):
    """Serializes an enriched watchlist entry row.

    Input is the dict built by the view from the domain data plus the
    best-effort quote lookup (WATCH-1 section K).
    """

    def to_representation(self, instance: dict[str, Any]) -> dict[str, Any]:
        latest_price = instance.get("latest_price")
        return {
            "id": str(instance["id"]),
            "account_id": str(instance["account_id"]),
            "instrument_token": instance["instrument_token"],
            "exchange": instance["exchange"],
            "tradingsymbol": instance["tradingsymbol"],
            "name": instance["name"],
            "note": instance["note"],
            "sort_order": instance["sort_order"],
            "latest_price": _fmt(latest_price) if latest_price is not None else None,
            "price_stale": instance["price_stale"],
            "created_at": instance["created_at"].isoformat(),
            "updated_at": instance["updated_at"].isoformat(),
        }
