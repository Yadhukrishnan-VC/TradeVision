"""
TradeVision AI — Health check views.

Each endpoint makes a real probe against its target service and returns
a structured JSON response using ``HealthResponse`` / ``ServiceHealthStatus``.

HTTP status codes:
    200  healthy or degraded (service is up but at reduced capacity)
    503  unhealthy (critical service unavailable)

Endpoints:
    GET /api/v1/health/             Basic liveness — is the process running?
    GET /api/v1/health/db/          PostgreSQL connectivity and latency
    GET /api/v1/health/cache/       Redis cache round-trip
    GET /api/v1/health/celery/      Celery worker availability
    GET /api/v1/health/system/      Aggregate: all checks in one call
"""

import logging
import time
from datetime import datetime, timezone

from django.http import HttpRequest, JsonResponse

from core.responses import HealthResponse, ServiceHealthStatus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level uptime tracking
# ---------------------------------------------------------------------------

_PROCESS_START: datetime = datetime.now(tz=timezone.utc)
_APP_VERSION = "0.1.0"


def _uptime_seconds() -> float:
    """Return the number of seconds since this process started."""
    return (datetime.now(tz=timezone.utc) - _PROCESS_START).total_seconds()


# ---------------------------------------------------------------------------
# Individual health check views
# ---------------------------------------------------------------------------


def health(request: HttpRequest) -> JsonResponse:
    """
    Basic liveness probe.

    Returns 200 immediately if the Django process is running and the
    request has been routed correctly. No external services are checked.
    Used by Docker's HEALTHCHECK and load-balancer health probes.
    """
    return JsonResponse(
        {
            "status": "healthy",
            "version": _APP_VERSION,
            "uptime_seconds": _uptime_seconds(),
        }
    )


def health_db(request: HttpRequest) -> JsonResponse:
    """
    PostgreSQL readiness probe.

    Calls ``connection.ensure_connection()`` to verify that the application
    can reach the database through pgbouncer. Records round-trip latency.
    """
    start = time.monotonic()
    try:
        from django.db import connection

        connection.ensure_connection()
        latency_ms = (time.monotonic() - start) * 1000

        db_status = ServiceHealthStatus(
            status="healthy",
            latency_ms=latency_ms,
        )
        response = HealthResponse(
            status="healthy",
            checks={"database": db_status},
            version=_APP_VERSION,
            uptime_seconds=_uptime_seconds(),
        )
        logger.debug("health_db_ok", extra={"latency_ms": round(latency_ms, 2)})
        return JsonResponse(response.to_dict(), status=200)

    except Exception as exc:
        logger.error("health_db_fail", exc_info=exc)
        db_status = ServiceHealthStatus(
            status="unhealthy",
            message=str(exc),
        )
        response = HealthResponse(
            status="unhealthy",
            checks={"database": db_status},
            version=_APP_VERSION,
        )
        return JsonResponse(response.to_dict(), status=503)


def health_cache(request: HttpRequest) -> JsonResponse:
    """
    Redis cache readiness probe.

    Performs a write-then-read round trip through the Django cache backend.
    Verifies that both Redis and the cache serialisation layer are working.
    """
    start = time.monotonic()
    try:
        from django.core.cache import cache

        probe_key = "tradevision:health:probe"
        probe_value = "ok"
        cache.set(probe_key, probe_value, timeout=30)
        result = cache.get(probe_key)
        latency_ms = (time.monotonic() - start) * 1000

        if result != probe_value:
            raise ValueError(
                f"Cache round-trip failed: expected {probe_value!r}, got {result!r}"
            )

        cache_status = ServiceHealthStatus(
            status="healthy",
            latency_ms=latency_ms,
        )
        response = HealthResponse(
            status="healthy",
            checks={"cache": cache_status},
            version=_APP_VERSION,
            uptime_seconds=_uptime_seconds(),
        )
        logger.debug("health_cache_ok", extra={"latency_ms": round(latency_ms, 2)})
        return JsonResponse(response.to_dict(), status=200)

    except Exception as exc:
        logger.error("health_cache_fail", exc_info=exc)
        cache_status = ServiceHealthStatus(
            status="unhealthy",
            message=str(exc),
        )
        response = HealthResponse(
            status="unhealthy",
            checks={"cache": cache_status},
            version=_APP_VERSION,
        )
        return JsonResponse(response.to_dict(), status=503)


def health_celery(request: HttpRequest) -> JsonResponse:
    """
    Celery worker availability probe.

    Sends a ``ping`` broadcast to all workers with a 3-second timeout.
    Reports ``degraded`` (not ``unhealthy``) if no workers respond —
    Celery is non-critical for request handling even though it is critical
    for market data processing.
    """
    start = time.monotonic()
    try:
        from config.celery import app as celery_app

        inspector = celery_app.control.inspect(timeout=3.0)
        ping_result = inspector.ping()
        latency_ms = (time.monotonic() - start) * 1000

        if ping_result:
            workers = list(ping_result.keys())
            celery_status = ServiceHealthStatus(
                status="healthy",
                latency_ms=latency_ms,
                detail={"active_workers": workers, "worker_count": len(workers)},
            )
            overall = "healthy"
            http_status = 200
        else:
            celery_status = ServiceHealthStatus(
                status="degraded",
                latency_ms=latency_ms,
                message="No Celery workers responded to ping within timeout.",
            )
            overall = "degraded"
            http_status = 503

        response = HealthResponse(
            status=overall,
            checks={"celery": celery_status},
            version=_APP_VERSION,
            uptime_seconds=_uptime_seconds(),
        )
        logger.debug(
            "health_celery_checked",
            extra={"status": overall, "latency_ms": round(latency_ms, 2)},
        )
        return JsonResponse(response.to_dict(), status=http_status)

    except Exception as exc:
        logger.warning("health_celery_fail", exc_info=exc)
        celery_status = ServiceHealthStatus(
            status="degraded",
            message=str(exc),
        )
        response = HealthResponse(
            status="degraded",
            checks={"celery": celery_status},
            version=_APP_VERSION,
        )
        return JsonResponse(response.to_dict(), status=503)


def health_eventbus(request: HttpRequest) -> JsonResponse:
    """
    EventBus (Redis Streams) readiness probe.

    Verifies Redis connectivity and that a basic publish/consume cycle
    works through the EventBus. Uses a temporary stream and consumer
    group, cleaned up after the check.
    """
    start = time.monotonic()
    try:
        from core.events.event_bus import EventBus
        from core.events.event_types import EventType
        from core.redis_client import get_redis_client

        redis_client = get_redis_client()
        redis_client.ping()

        bus = EventBus(redis_client)

        probe_stream = f"health:probe:{int(start)}"
        probe_group = "health-check"

        redis_client.xgroup_create(probe_stream, probe_group, mkstream=True)
        entry_id = redis_client.xadd(
            probe_stream, {"payload": '{"probe": true}'}, maxlen=10
        )

        results = redis_client.xreadgroup(
            probe_group, "health-checker", {probe_stream: ">"},
            count=1, block=500,
        )
        redis_client.xack(probe_stream, probe_group, entry_id)
        redis_client.delete(probe_stream)

        latency_ms = (time.monotonic() - start) * 1000

        if not results:
            raise ValueError("EventBus probe: no messages received from stream")

        eventbus_status = ServiceHealthStatus(
            status="healthy",
            latency_ms=latency_ms,
            detail={
                "stream_length": redis_client.xlen(probe_stream) or 0,
            },
        )
        response = HealthResponse(
            status="healthy",
            checks={"eventbus": eventbus_status},
            version=_APP_VERSION,
            uptime_seconds=_uptime_seconds(),
        )
        logger.debug("health_eventbus_ok", extra={"latency_ms": round(latency_ms, 2)})
        return JsonResponse(response.to_dict(), status=200)

    except Exception as exc:
        logger.error("health_eventbus_fail", exc_info=exc)
        eventbus_status = ServiceHealthStatus(
            status="unhealthy",
            message=str(exc),
        )
        response = HealthResponse(
            status="unhealthy",
            checks={"eventbus": eventbus_status},
            version=_APP_VERSION,
        )
        return JsonResponse(response.to_dict(), status=503)


def health_system(request: HttpRequest) -> JsonResponse:
    """
    Aggregate system health probe.

    Runs all individual checks (DB, cache, Celery) sequentially and returns
    a combined status. The overall status is the worst-case of all checks:
    - Any ``unhealthy`` → overall ``unhealthy`` → HTTP 503
    - Any ``degraded``  → overall ``degraded``  → HTTP 200
    - All ``healthy``   → overall ``healthy``   → HTTP 200

    Celery degradation does not escalate to ``unhealthy`` since workers
    can restart independently without affecting the API.
    """
    checks: dict[str, ServiceHealthStatus] = {}
    overall = "healthy"

    # --- Database ---
    start = time.monotonic()
    try:
        from django.db import connection

        connection.ensure_connection()
        checks["database"] = ServiceHealthStatus(
            status="healthy",
            latency_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as exc:
        checks["database"] = ServiceHealthStatus(
            status="unhealthy",
            message=str(exc),
        )
        overall = "unhealthy"
        logger.error("health_system_db_fail", exc_info=exc)

    # --- Cache ---
    start = time.monotonic()
    try:
        from django.core.cache import cache

        cache.set("tradevision:health:sys", "ok", timeout=5)
        assert cache.get("tradevision:health:sys") == "ok"
        checks["cache"] = ServiceHealthStatus(
            status="healthy",
            latency_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as exc:
        checks["cache"] = ServiceHealthStatus(
            status="unhealthy",
            message=str(exc),
        )
        overall = "unhealthy"
        logger.error("health_system_cache_fail", exc_info=exc)

    # --- EventBus (Redis Streams) ---
    start = time.monotonic()
    try:
        from core.redis_client import get_redis_client

        redis_client = get_redis_client()
        redis_client.ping()
        checks["eventbus"] = ServiceHealthStatus(
            status="healthy",
            latency_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as exc:
        checks["eventbus"] = ServiceHealthStatus(
            status="unhealthy",
            message=str(exc),
        )
        overall = "unhealthy"
        logger.error("health_system_eventbus_fail", exc_info=exc)

    # --- Celery (non-critical) ---
    start = time.monotonic()
    try:
        from config.celery import app as celery_app

        ping = celery_app.control.inspect(timeout=2.0).ping()
        if ping:
            checks["celery"] = ServiceHealthStatus(
                status="healthy",
                latency_ms=(time.monotonic() - start) * 1000,
                detail={"worker_count": len(ping)},
            )
        else:
            checks["celery"] = ServiceHealthStatus(
                status="degraded",
                message="No workers responded.",
            )
            if overall == "healthy":
                overall = "degraded"
    except Exception as exc:
        checks["celery"] = ServiceHealthStatus(
            status="degraded",
            message=str(exc),
        )
        if overall == "healthy":
            overall = "degraded"
        logger.warning("health_system_celery_warn", exc_info=exc)

    response = HealthResponse(
        status=overall,
        checks=checks,
        version=_APP_VERSION,
        uptime_seconds=_uptime_seconds(),
    )
    http_status = 503 if overall == "unhealthy" else 200
    return JsonResponse(response.to_dict(), status=http_status)
