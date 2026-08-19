"""CorrelationIdMiddleware tests.

Contract: every response carries an ``X-Correlation-ID``; the middleware
echoes an inbound ``X-Correlation-ID`` header, or generates a UUID when
absent; it also sets ``request.correlation_id`` and the logging context.
"""

from __future__ import annotations

import uuid

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


class TestCorrelationIdMiddleware:
    def test_generates_correlation_id_when_absent(self) -> None:
        response = Client().get("/api/v1/health/")
        correlation_id = response.headers["X-Correlation-ID"]
        assert uuid.UUID(correlation_id)  # valid UUID4
        assert response.status_code == 200

    def test_echoes_inbound_correlation_id(self) -> None:
        response = Client().get("/api/v1/health/", headers={"X-Correlation-ID": "trace-abc-123"})
        assert response.headers["X-Correlation-ID"] == "trace-abc-123"

    def test_generates_different_ids_across_requests(self) -> None:
        client = Client()
        first = client.get("/api/v1/health/").headers["X-Correlation-ID"]
        second = client.get("/api/v1/health/").headers["X-Correlation-ID"]
        assert first != second
        assert uuid.UUID(first)
        assert uuid.UUID(second)