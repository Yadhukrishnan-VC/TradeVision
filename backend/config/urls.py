"""
TradeVision AI — Root URL configuration.

URL structure:
    /admin/             Django administration interface
    /api/v1/health/     Liveness probe (Docker health check + load balancer)
    /api/v1/            Versioned REST API (routes registered by each app)
    /metrics/           Prometheus metrics scrape endpoint
"""

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.urls import path
from django_prometheus import exports as prometheus_exports


def health_check(request: HttpRequest) -> HttpResponse:
    """
    Lightweight liveness probe.

    Returns HTTP 200 when Django and its middleware stack are operational.
    A deeper readiness probe (DB + Redis connectivity) is added in Phase 1.
    """
    return HttpResponse("ok", content_type="text/plain", status=200)


urlpatterns = [
    # Django admin — protected by authentication
    path("admin/", admin.site.urls),

    # Health and observability — unauthenticated, not throttled
    path("api/v1/health/", health_check, name="health-check"),
    path("metrics/", prometheus_exports.ExportToDjangoView, name="prometheus-metrics"),

    # Versioned API — app-level url confs are included here as each phase
    # introduces its endpoints. Example:
    #   path("api/v1/market-data/", include("apps.market_data.urls")),
]
