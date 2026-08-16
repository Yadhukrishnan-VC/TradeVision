"""CORS header tests for the P0 auth + CORS wiring.

Verifies the CorsMiddleware added in Phase 3 behaves correctly:
  * an allowed frontend origin receives Access-Control-Allow-Origin
  * a disallowed origin does not receive the unrestricted allow-origin header
  * same-origin requests keep working
  * CORS_ALLOW_CREDENTIALS stays off (header-based auth, no cookies)
"""

from __future__ import annotations

import pytest
from django.test import override_settings

pytestmark = pytest.mark.django_db

ALLOWED_ORIGIN = "https://tradevision.example.com"
DISALLOWED_ORIGIN = "https://evil.example.com"

_CORS_OVERRIDES = {
    "CORS_ALLOW_ALL_ORIGINS": False,
    "CORS_ALLOWED_ORIGINS": [ALLOWED_ORIGIN],
    "CORS_ALLOW_CREDENTIALS": False,
}


@override_settings(**_CORS_OVERRIDES)
def test_allowed_origin_gets_cors_header(api_client) -> None:
    response = api_client.get(
        "/api/v1/health/",
        HTTP_ORIGIN=ALLOWED_ORIGIN,
    )
    assert response["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN


@override_settings(**_CORS_OVERRIDES)
def test_allowed_origin_preflight(api_client) -> None:
    response = api_client.options(
        "/api/v1/health/",
        HTTP_ORIGIN=ALLOWED_ORIGIN,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,content-type",
    )
    assert response.status_code == 200
    assert response["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
    assert "authorization" in response["Access-Control-Allow-Headers"].lower()


@override_settings(**_CORS_OVERRIDES)
def test_disallowed_origin_receives_no_cors_allow_origin(api_client) -> None:
    response = api_client.get(
        "/api/v1/health/",
        HTTP_ORIGIN=DISALLOWED_ORIGIN,
    )
    assert "Access-Control-Allow-Origin" not in response


@override_settings(**_CORS_OVERRIDES)
def test_no_origin_has_no_cors_header(api_client) -> None:
    response = api_client.get("/api/v1/health/")
    assert "Access-Control-Allow-Origin" not in response


@override_settings(**_CORS_OVERRIDES)
def test_credentials_not_allowed(api_client) -> None:
    response = api_client.get(
        "/api/v1/health/",
        HTTP_ORIGIN=ALLOWED_ORIGIN,
    )
    # Header-based auth (JWT Bearer / Api-Key), no cookies => credentials
    # must stay off. django-cors-headers emits the header only when enabled.
    assert response.get("Access-Control-Allow-Credentials") != "true"