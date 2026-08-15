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


class CostSensitivitySerializer(serializers.Serializer):
    """Request body for a per-rule cost-sensitivity (commission/slippage) sweep."""

    symbol = serializers.CharField(max_length=100)
    timeframe = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    range_start = serializers.DateTimeField()
    range_end = serializers.DateTimeField()
    commission_start = serializers.DecimalField(max_digits=10, decimal_places=6)
    commission_end = serializers.DecimalField(max_digits=10, decimal_places=6)
    commission_step = serializers.DecimalField(max_digits=10, decimal_places=6)
    slippage_start = serializers.DecimalField(max_digits=10, decimal_places=4)
    slippage_end = serializers.DecimalField(max_digits=10, decimal_places=4)
    slippage_step = serializers.DecimalField(max_digits=10, decimal_places=4)
    initial_capital = serializers.DecimalField(
        max_digits=20,
        decimal_places=8,
        required=False,
        default=Decimal(1000000),
    )

    def validate(self, attrs: dict) -> dict:
        if attrs["range_end"] <= attrs["range_start"]:
            raise serializers.ValidationError("range_end must be after range_start")
        if attrs["commission_step"] <= 0:
            raise serializers.ValidationError("commission_step must be positive")
        if attrs["slippage_step"] <= 0:
            raise serializers.ValidationError("slippage_step must be positive")
        if attrs["commission_end"] < attrs["commission_start"]:
            raise serializers.ValidationError(
                "commission_end must be >= commission_start"
            )
        if attrs["slippage_end"] < attrs["slippage_start"]:
            raise serializers.ValidationError("slippage_end must be >= slippage_start")

        from apps.backtesting.application.cost_sensitivity_service import (
            MAX_GRID_POINTS,
            generate_cost_grid,
        )

        grid = generate_cost_grid(
            (attrs["commission_start"], attrs["commission_end"]),
            attrs["commission_step"],
            (attrs["slippage_start"], attrs["slippage_end"]),
            attrs["slippage_step"],
        )
        if len(grid) > MAX_GRID_POINTS:
            raise serializers.ValidationError(
                f"cost grid of {len(grid)} points exceeds the "
                f"{MAX_GRID_POINTS} point limit"
            )
        return attrs


class EdgeValidationSerializer(serializers.Serializer):
    """Request body for a per-rule empirical edge evaluation.

    Reports ``has_edge`` per rule that traded over the range at the zero-cost
    baseline and at a caller-supplied realistic cost, plus the aggregate
    walk-forward OOS distribution. Overlaps with ``WalkForwardSerializer`` by
    design: the edge report is defined as the single-run metrics joined with
    the walk-forward distribution over the same range.
    """

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
    realistic_commission_rate = serializers.DecimalField(
        max_digits=10,
        decimal_places=6,
        required=False,
        default=Decimal("0.0003"),
    )
    realistic_slippage_bps = serializers.DecimalField(
        max_digits=10,
        decimal_places=4,
        required=False,
        default=Decimal("5.0"),
    )
    initial_capital = serializers.DecimalField(
        max_digits=20,
        decimal_places=8,
        required=False,
        default=Decimal(1000000),
    )

    def validate(self, attrs: dict) -> dict:
        if attrs["range_end"] <= attrs["range_start"]:
            raise serializers.ValidationError("range_end must be after range_start")
        if attrs["realistic_commission_rate"] < 0:
            raise serializers.ValidationError(
                "realistic_commission_rate must not be negative"
            )
        if attrs["realistic_slippage_bps"] < 0:
            raise serializers.ValidationError("realistic_slippage_bps must not be negative")
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
        default=Decimal(1000000),
    )

    def validate(self, attrs: dict) -> dict:
        if attrs["range_end"] <= attrs["range_start"]:
            raise serializers.ValidationError("range_end must be after range_start")
        return attrs
