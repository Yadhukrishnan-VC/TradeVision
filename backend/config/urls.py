"""
TradeVision AI — Root URL configuration.

URL structure:
    /admin/             Django administration interface
    /api/v1/health/     Liveness probe (Docker health check + load balancer)
    /api/v1/auth/       Authentication and user profile endpoints
    /api/v1/            Versioned REST API (routes registered by each app)
    /metrics/           Prometheus metrics scrape endpoint
"""

from django.contrib import admin
from django.urls import include, path
from django_prometheus import exports as prometheus_exports

urlpatterns = [
    # Django admin — protected by authentication
    path("admin/", admin.site.urls),

    # Health and observability — unauthenticated, not throttled
    path("api/v1/health/", include("apps.health.urls")),
    path("metrics/", prometheus_exports.ExportToDjangoView, name="prometheus-metrics"),

    # Authentication and user profile
    path("api/v1/auth/", include("apps.accounts.urls")),

    # Versioned API — app-level url confs are included here as each phase
    # introduces its endpoints. Example:
    #   path("api/v1/market-data/", include("apps.market_data.urls")),
]
