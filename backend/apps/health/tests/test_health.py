"""Health check endpoint tests (apps/health).

The probes hit real dependencies where deterministic (PostgreSQL in the test
env, Redis in local/CI) and mock only the non-deterministic Celery worker
broadcast. Cache behaviour is pinned via ``override_settings``.

Contract (from ``views.py`` + ``urls.py`` docstrings):
    200 healthy or degraded, 503 unhealthy.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.test import Client, override_settings

from config.celery import app as celery_app

pytestmark = pytest.mark.django_db


@pytest.fixture
def client() -> Client:
    return Client()


class TestLiveness:
    def test_returns_healthy_with_version_and_uptime(self, client: Client) -> None:
        response = client.get("/api/v1/health/")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert isinstance(body["version"], str)
        assert isinstance(body["uptime_seconds"], (int, float))


class TestDatabaseProbe:
    def test_returns_healthy(self, client: Client) -> None:
        response = client.get("/api/v1/health/db/")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["checks"]["database"]["status"] == "healthy"
        assert response.json()["checks"]["database"]["latency_ms"] >= 0


class TestCacheProbe:
    def test_returns_healthy_with_working_cache(self, client: Client) -> None:
        with override_settings(
            CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
        ):
            response = client.get("/api/v1/health/cache/")
        assert response.status_code == 200
        assert response.json()["checks"]["cache"]["status"] == "healthy"

    def test_returns_503_when_cache_does_not_roundtrip(self, client: Client) -> None:
        # testing.py sets DummyCache, which never stores -> probe must report unhealthy.
        response = client.get("/api/v1/health/cache/")
        assert response.status_code == 503
        assert response.json()["status"] == "unhealthy"
        assert response.json()["checks"]["cache"]["status"] == "unhealthy"


class TestCeleryProbe:
    def _patch_ping(self, result) -> MagicMock:
        inspector = MagicMock()
        inspector.ping.return_value = result
        control = MagicMock()
        control.inspect.return_value = inspector
        return patch.object(celery_app, "control", control)

    def test_degraded_when_no_workers(self, client: Client) -> None:
        with self._patch_ping({}):
            response = client.get("/api/v1/health/celery/")
        assert response.status_code == 503
        assert response.json()["status"] == "degraded"
        assert response.json()["checks"]["celery"]["status"] == "degraded"

    def test_healthy_when_workers_respond(self, client: Client) -> None:
        with self._patch_ping({"worker@w1": {"ok": "pong"}}):
            response = client.get("/api/v1/health/celery/")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["checks"]["celery"]["status"] == "healthy"
        assert body["checks"]["celery"]["detail"]["worker_count"] == 1

    def test_degraded_when_ping_errors(self, client: Client) -> None:
        inspector = MagicMock()
        inspector.ping.side_effect = RuntimeError("broker down")
        control = MagicMock()
        control.inspect.return_value = inspector
        with patch.object(celery_app, "control", control):
            response = client.get("/api/v1/health/celery/")
        assert response.status_code == 503
        assert response.json()["checks"]["celery"]["status"] == "degraded"


class TestEventBusProbe:
    def test_returns_healthy_against_redis(self, client: Client) -> None:
        response = client.get("/api/v1/health/eventbus/")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["checks"]["eventbus"]["status"] == "healthy"


class TestSystemProbe:
    def test_degraded_when_celery_has_no_workers(self, client: Client) -> None:
        inspector = MagicMock()
        inspector.ping.return_value = {}
        control = MagicMock()
        control.inspect.return_value = inspector
        with patch.object(celery_app, "control", control), override_settings(
            CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
        ):
            response = client.get("/api/v1/health/system/")
        assert response.status_code == 200
        assert response.json()["status"] == "degraded"
        assert response.json()["checks"]["celery"]["status"] == "degraded"

    def test_unhealthy_when_cache_fails(self, client: Client) -> None:
        inspector = MagicMock()
        inspector.ping.return_value = {"worker@w1": {"ok": "pong"}}
        control = MagicMock()
        control.inspect.return_value = inspector
        with patch.object(celery_app, "control", control):
            response = client.get("/api/v1/health/system/")
        assert response.status_code == 503
        assert response.json()["status"] == "unhealthy"
        assert response.json()["checks"]["cache"]["status"] == "unhealthy"