from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

dashboard_home_summary_staleness_seconds = Gauge(
    "dashboard_home_summary_staleness_seconds",
    "Time since the dashboard home summary was last updated",
    ["account_id"],
)

dashboard_home_requests_total = Counter(
    "dashboard_home_requests_total",
    "Total number of dashboard home requests",
    ["status_code"],
)

dashboard_home_cache_hit_ratio = Gauge(
    "dashboard_home_cache_hit_ratio",
    "Cache hit ratio for dashboard home summary",
)

dashboard_portfolio_price_lag_ms = Gauge(
    "dashboard_portfolio_price_lag_ms",
    "Time since last PriceTick per symbol",
    ["symbol"],
)

dashboard_portfolio_reconciliation_divergence_count = Counter(
    "dashboard_portfolio_reconciliation_divergence_count",
    "Count of reconciliation divergences detected",
    ["account_id"],
)

dashboard_live_positions_websocket_connections = Gauge(
    "dashboard_live_positions_websocket_connections",
    "Current number of live positions WebSocket connections",
)

dashboard_live_positions_broadcast_latency_ms = Histogram(
    "dashboard_live_positions_broadcast_latency_ms",
    "Latency of position broadcast from event consumption to WebSocket send",
    buckets=[5, 10, 25, 50, 100, 250, 500, 1000, 5000],
)

dashboard_order_projection_lag_seconds = Histogram(
    "dashboard_order_projection_lag_seconds",
    "Lag between event occurred_at and projection applied_at",
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60],
)

dashboard_order_dead_letter_total = Counter(
    "dashboard_order_dead_letter_total",
    "Total number of order events sent to dead letter queue",
    ["event_type"],
)

dashboard_trade_export_duration_seconds = Histogram(
    "dashboard_trade_export_duration_seconds",
    "Duration of trade history export generation",
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
)

dashboard_trade_export_failures_total = Counter(
    "dashboard_trade_export_failures_total",
    "Total number of failed trade exports",
    ["reason"],
)
