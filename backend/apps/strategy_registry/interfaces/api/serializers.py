from __future__ import annotations

from rest_framework import serializers

from apps.strategy_registry.models import StrategySymbolAffinity, TradingStrategy


class TradingStrategySerializer(serializers.ModelSerializer):
    class Meta:
        model = TradingStrategy
        fields = (
            "id",
            "name",
            "status",
            "priority",
            "symbol_filter",
            "sector_filter",
            "preferred_provider",
            "confidence_threshold",
            "risk_threshold",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class TradingStrategyUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradingStrategy
        fields = (
            "name",
            "status",
            "priority",
            "symbol_filter",
            "sector_filter",
            "preferred_provider",
            "confidence_threshold",
            "risk_threshold",
        )
        extra_kwargs = {
            "name": {"required": False},
            "status": {"required": False},
            "priority": {"required": False},
            "confidence_threshold": {"required": False},
            "risk_threshold": {"required": False},
        }


class TradingStrategyCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradingStrategy
        fields = (
            "name",
            "status",
            "priority",
            "symbol_filter",
            "sector_filter",
            "preferred_provider",
            "confidence_threshold",
            "risk_threshold",
            "created_at",
            "updated_at",
        )


class StrategySymbolAffinitySerializer(serializers.ModelSerializer):
    strategy = TradingStrategySerializer(read_only=True)

    class Meta:
        model = StrategySymbolAffinity
        fields = (
            "id",
            "strategy",
            "symbol",
            "rank",
            "score",
            "expectancy",
            "profit_factor",
            "sharpe_ratio",
            "max_drawdown_pct",
            "trade_count",
            "evaluated_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields