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

from django.conf import settings
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

    # Ingestion Webhook API — external webhook front door (TradingView,
    # Chartink) plus a staff-only raw-event debug listing.
    path("api/v1/ingestion/", include("apps.ingestion.interfaces.api.urls")),

    # Technical Analysis Webhook API — Batch 3
    path("api/v1/technical-analysis/", include("apps.technical_analysis.interfaces.api.urls")),

    # Pattern Engine API — Batch AI-5
    path("api/v1/pattern-engine/", include("apps.pattern_engine.interfaces.api.urls")),

    # Risk Management API — Batch M3
    path("api/v1/risk-management/", include("apps.risk_management.interfaces.api.urls")),

    # Portfolio API — Batch M4
    path("api/v1/portfolio/", include("apps.portfolio.interfaces.api.urls")),

    # Execution API — Milestone B: Safe Paper Execution Engine (read-only
    # order/request visibility; submission happens via risk_management).
    path("api/v1/execution/", include("apps.execution.interfaces.api.urls")),

    # Backtesting API — Batch M3: Historical Replay & Backtesting Engine.
    path("api/v1/backtesting/", include("apps.backtesting.interfaces.api.urls")),

    # Watchlist API — WATCH-1: Per-account User Watchlist.
    path("api/v1/watchlist/", include("apps.watchlist.interfaces.api.urls")),

    # Pipeline Health API — PIPELINE-HEALTH-1: Forward paper-trading
    # pipeline health & staleness monitoring (operator-facing, read-only).
    path("api/v1/pipeline-health/", include("apps.pipeline_health.interfaces.api.urls")),

    # Portfolio Reconciliation API — PORTFOLIO-RECONCILE-1: read-only drift
    # detection log for the dashboard read model (OWNER/STAFF only).
    path(
        "api/v1/portfolio-reconciliation/",
        include(
            "apps.portfolio_reconciliation.interfaces.api.urls"
        ),
    ),

    # News Feed API — NEWS-FEED-1: licensed news provider (Marketaux).
    # Read-only ingested headlines + provider sentiment; paginated.
    path("api/v1/news/", include("apps.news_feed.interfaces.api.urls")),
]

# Django Debug Toolbar (development only) — registers the "djdt" namespace
# its panels reverse against when rendering the toolbar.
if settings.DEBUG and "debug_toolbar" in settings.INSTALLED_APPS:
    urlpatterns.append(path("__debug__/", include("debug_toolbar.urls")))
