"""
TradeVision AI — Root URL configuration.

URL structure:
    /admin/             Django administration interface
    /api/v1/health/     Liveness probe (Docker health check + load balancer)
    /api/v1/auth/       Authentication and user profile endpoints
    /api/v1/            Versioned REST API (routes registered by each app)
    /metrics/           Prometheus metrics scrape endpoint
"""

from __future__ import annotations

from django.contrib import admin
from django.urls import include, path
from django_prometheus import exports as prometheus_exports

urlpatterns = [
    path("admin/", admin.site.urls),

    # Authentication and user profile
    path("api/v1/auth/", include("apps.accounts.interfaces.api.urls")),

    # Health and observability — unauthenticated, not throttled
    path("api/v1/health/", include("apps.health.urls")),
    path("metrics/", prometheus_exports.ExportToDjangoView, name="prometheus-metrics"),

    # Versioned API — app-level url confs are included here as each phase
    # introduces its endpoints. Example:
    #   path("api/v1/market-data/", include("apps.market_data.urls")),

    # Dashboard API — Batch D1: Trading Core Dashboard
    path("api/v1/dashboard/", include("apps.dashboard.interfaces.api.trading_core.urls")),

    # Dashboard API — Batch D2: Analytics & Risk
    path("api/v1/dashboard/", include("apps.dashboard.interfaces.api.analytics_risk.urls")),

    # Journal API — Batch 1: Trade Journal
    path("api/v1/journal/", include("apps.journal.interfaces.api.urls")),

    # Audit Log API — Batch 1: Compliance Audit Trail
    path("api/v1/audit/", include("apps.audit_log.urls")),

    # Rule Engine API
    path("api/v1/rule-engine/", include("apps.rule_engine.interfaces.api.urls")),

    # Recommendations API
    path("api/v1/recommendations/", include("apps.recommendations.interfaces.api.urls")),

    # Trader Memory API
    path("api/v1/trader-memory/", include("apps.trader_memory.interfaces.api.urls")),

    # Signals Engine API — Batch 2
    path("api/v1/signals/", include("apps.signals_engine.interfaces.api.urls")),
]
