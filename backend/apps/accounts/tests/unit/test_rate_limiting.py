"""WS2 — API rate limiting regression tests.

Exercises the DRF throttle configuration added in ``config/settings/base.py``
(DEFAULT_THROTTLE_CLASSES / DEFAULT_THROTTLE_RATES) and the scoped throttles on
the auth + API-key endpoints.

Approach: the throttles read their counters from ``SimpleRateThrottle.cache``,
which is a class attribute bound at import time. Tests therefore bind a fresh
``LocMemCache`` to it directly (deterministic, no shared state) and set tiny
rates per test so the limit is hit in a handful of requests.
"""

from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.cache.backends.locmem import LocMemCache
from rest_framework import status
from rest_framework.throttling import SimpleRateThrottle

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def throttle_store(monkeypatch) -> LocMemCache:
    """Bind a fresh in-memory counter store to the DRF throttle classes."""
    store = LocMemCache("throttle_test", {})
    monkeypatch.setattr(SimpleRateThrottle, "cache", store)
    return store


@pytest.fixture
def set_rates(monkeypatch):
    def _apply(rates: dict[str, str]) -> None:
        full = {
            "anon": "1000/hour",
            "user": "1000/hour",
            "auth": "1000/hour",
            "api_keys": "1000/hour",
            **rates,
        }
        monkeypatch.setattr(SimpleRateThrottle, "THROTTLE_RATES", full)

    return _apply


@pytest.fixture
def trader() -> object:
    return User.objects.create_user(
        username=f"trader-{uuid.uuid4().hex[:8]}",
        password="SecurePass123!",
    )


def _login(client, username: str, password: str = "SecurePass123!") -> object:
    return client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": password},
        format="json",
    )


class TestUserRateThrottle:
    def test_user_throttle_limits_per_user(
        self, api_client, throttle_store, set_rates, trader
    ) -> None:
        set_rates({"user": "2/min"})
        api_client.force_authenticate(user=trader)

        first = api_client.get("/api/v1/auth/me/")
        second = api_client.get("/api/v1/auth/me/")
        third = api_client.get("/api/v1/auth/me/")

        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK
        assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_user_throttle_is_per_user(
        self, api_client, throttle_store, set_rates, trader
    ) -> None:
        """User B is not penalised for user A's requests."""
        set_rates({"user": "2/min"})
        api_client.force_authenticate(user=trader)
        api_client.get("/api/v1/auth/me/")
        api_client.get("/api/v1/auth/me/")
        api_client.get("/api/v1/auth/me/")
        assert api_client.get("/api/v1/auth/me/").status_code == status.HTTP_429_TOO_MANY_REQUESTS

        other = User.objects.create_user(
            username=f"trader-{uuid.uuid4().hex[:8]}",
            password="SecurePass123!",
        )
        api_client.force_authenticate(user=other)
        assert api_client.get("/api/v1/auth/me/").status_code == status.HTTP_200_OK


class TestAnonRateThrottle:
    def test_anon_throttle_limits_per_ip(
        self, api_client, throttle_store, set_rates, trader
    ) -> None:
        set_rates({"anon": "2/min"})
        first = _login(api_client, trader.username)
        second = _login(api_client, trader.username)
        third = _login(api_client, trader.username)
        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK
        assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS


class TestAuthScopeThrottle:
    def test_login_endpoint_has_stricter_auth_scope(
        self, api_client, throttle_store, set_rates, trader
    ) -> None:
        """The auth scope on login is enforced independently of anon/user."""
        set_rates({"auth": "2/min"})
        api_client.force_authenticate(user=trader)
        _login(api_client, trader.username)
        _login(api_client, trader.username)
        assert _login(api_client, trader.username).status_code == status.HTTP_429_TOO_MANY_REQUESTS


class TestAPIKeyScopeThrottle:
    def test_api_key_creation_throttled(
        self, api_client, throttle_store, set_rates, trader
    ) -> None:
        set_rates({"api_keys": "2/min"})
        api_client.force_authenticate(user=trader)
        payload = {"name": "t", "scopes": ["read:portfolio"]}
        first = api_client.post("/api/v1/auth/api-keys/", payload, format="json")
        second = api_client.post("/api/v1/auth/api-keys/", payload, format="json")
        third = api_client.post("/api/v1/auth/api-keys/", payload, format="json")
        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_201_CREATED
        assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS


class TestThrottleReset:
    def test_throttle_allows_after_window_elapses(
        self, api_client, throttle_store, set_rates, trader, monkeypatch
    ) -> None:
        set_rates({"user": "2/min"})
        api_client.force_authenticate(user=trader)
        api_client.get("/api/v1/auth/me/")
        api_client.get("/api/v1/auth/me/")
        assert api_client.get("/api/v1/auth/me/").status_code == status.HTTP_429_TOO_MANY_REQUESTS

        # Simulate the rate window elapsing: clear the counter store.
        throttle_store.clear()
        assert api_client.get("/api/v1/auth/me/").status_code == status.HTTP_200_OK


class TestConfig:
    def test_throttle_rates_are_configured(self) -> None:
        from rest_framework.settings import api_settings

        rates = api_settings.DEFAULT_THROTTLE_RATES
        assert "anon" in rates
        assert "user" in rates
        assert "auth" in rates
        assert "api_keys" in rates

    def test_default_throttle_classes_configured(self) -> None:
        from rest_framework.settings import api_settings

        classes = api_settings.DEFAULT_THROTTLE_CLASSES
        class_names = [getattr(cls, "__name__", str(cls)) for cls in classes]
        assert "AnonRateThrottle" in class_names
        assert "UserRateThrottle" in class_names
        assert "ScopedRateThrottle" in class_names