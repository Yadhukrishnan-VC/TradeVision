from __future__ import annotations

from rest_framework import serializers

from apps.dashboard.domain.analytics_risk.value_objects import Granularity, Period


class PeriodQuerySerializer(serializers.Serializer):
    period = serializers.ChoiceField(choices=[p.value for p in Period], default=Period.ALL_TIME.value)
    granularity = serializers.ChoiceField(choices=[g.value for g in Granularity], default=Granularity.DAILY.value)


class PnLSummaryResponseSerializer(serializers.Serializer):
    current_total_pnl = serializers.DecimalField(max_digits=20, decimal_places=8)
    current_unrealized_pnl = serializers.DecimalField(max_digits=20, decimal_places=8)
    peak_cumulative_pnl = serializers.DecimalField(max_digits=20, decimal_places=8)
    current_drawdown_pct = serializers.DecimalField(max_digits=10, decimal_places=4)
    time_series = serializers.ListField(child=serializers.DictField())
    metadata = serializers.DictField()


class DailyRollupResponseSerializer(serializers.Serializer):
    trading_date = serializers.CharField()
    realized_pnl = serializers.DecimalField(max_digits=20, decimal_places=8)
    total_pnl = serializers.DecimalField(max_digits=20, decimal_places=8)
    cumulative_pnl = serializers.DecimalField(max_digits=20, decimal_places=8)


class PerformanceResponseSerializer(serializers.Serializer):
    period = serializers.CharField()
    win_rate = serializers.DecimalField(max_digits=6, decimal_places=4)
    avg_win = serializers.DecimalField(max_digits=20, decimal_places=8)
    avg_loss = serializers.DecimalField(max_digits=20, decimal_places=8)
    profit_factor = serializers.DecimalField(max_digits=10, decimal_places=4, allow_null=True)
    expectancy = serializers.DecimalField(max_digits=20, decimal_places=8)
    sharpe_like_ratio = serializers.DecimalField(max_digits=10, decimal_places=4, allow_null=True)
    total_trades = serializers.IntegerField()
    winning_trades = serializers.IntegerField()
    losing_trades = serializers.IntegerField()


class RiskSummaryResponseSerializer(serializers.Serializer):
    total_exposure = serializers.DecimalField(max_digits=20, decimal_places=8)
    largest_position_pct = serializers.DecimalField(max_digits=6, decimal_places=4)
    sector_concentration_pct = serializers.DecimalField(max_digits=6, decimal_places=4)
    leverage_ratio = serializers.DecimalField(max_digits=10, decimal_places=4)
    active_alerts = serializers.ListField(child=serializers.DictField())
