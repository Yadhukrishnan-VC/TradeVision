"""
TradeVision AI — Health check URL configuration.

Included under ``/api/v1/health/`` in ``config/urls.py``.

Routes:
    GET /api/v1/health/             Liveness probe
    GET /api/v1/health/db/          Database probe
    GET /api/v1/health/cache/       Redis cache probe
    GET /api/v1/health/celery/      Celery worker probe
    GET /api/v1/health/eventbus/    EventBus (Redis Streams) probe
    GET /api/v1/health/system/      Aggregate probe (all checks)

All endpoints are unauthenticated and not rate-throttled so that
Docker health checks and external monitoring systems can reach them
without credentials.
"""

from django.urls import path

from . import views

app_name = "health"

urlpatterns = [
    path("", views.health, name="liveness"),
    path("db/", views.health_db, name="database"),
    path("cache/", views.health_cache, name="cache"),
    path("celery/", views.health_celery, name="celery"),
    path("eventbus/", views.health_eventbus, name="eventbus"),
    path("system/", views.health_system, name="system"),
]
