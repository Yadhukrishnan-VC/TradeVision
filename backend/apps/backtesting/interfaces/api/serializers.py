"""Batch M3 — Backtest run API serializers."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers


class BacktestRunCreateSerializer(serializers.Serializer):
    """Request body for creating a backtest run."""

    symbol = serializers.CharField(max_length=100)
    timeframe = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    range_start = serializers.DateTimeField()
    range_end = serializers.DateTimeField()
    initial_capital = serializers.DecimalField(
        max_digits=20,
        decimal_places=8,
        required=False,
        default=1000000,
    )

    def validate(self, attrs: dict) -> dict:
        if attrs["range_end"] <= attrs["range_start"]:
            raise serializers.ValidationError("range_end must be after range_start")
        return attrs


class BacktestRunStatsSerializer(serializers.Serializer):
    """Read-only run status + stats payload."""

    run_id = serializers.UUIDField(source="id")
    status = serializers.CharField()
    account_id = serializers.UUIDField()
    symbol = serializers.CharField()
    timeframe = serializers.CharField()
    range_start = serializers.DateTimeField()
    range_end = serializers.DateTimeField()
    failure_reason = serializers.CharField()
    started_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)
    stats = serializers.DictField(read_only=True)


class WalkForwardSerializer(serializers.Serializer):
    """Request body for a walk-forward validation run."""

    symbol = serializers.CharField(max_length=100)
    timeframe = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    range_start = serializers.DateTimeField()
    range_end = serializers.DateTimeField()
    window_size_days = serializers.IntegerField(min_value=1)
    step_size_days = serializers.IntegerField(min_value=1)
    in_sample_ratio = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        default=Decimal("0.70"),
    )
    initial_capital = serializers.DecimalField(
        max_digits=20,
        decimal_places=8,
        required=False,
        default=Decimal("1000000"),
    )

    def validate(self, attrs: dict) -> dict:
        if attrs["range_end"] <= attrs["range_start"]:
            raise serializers.ValidationError("range_end must be after range_start")
        return attrs
