"""Cross-account ownership (IDOR/BOLA) regression tests for analytics REST views.

The four analytics endpoints (pnl, pnl/daily, performance, risk) accept an
``account_id`` URL parameter. They must only return the *caller's own* data:
a JWT user must not read another user's account, and an API key must not read
an account that is not the key owner's. Violations return 404 so that the
existence of other accounts is not disclosed.

These tests exercise the real JWTAuthentication + APIKeyAuthentication over
real HTTP (no force_authenticate).
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.domain.value_objects import Role, Scope

pytestmark = pytest.mark.django_db

User = get_user_model()

PNL_URL = "/api/v1/dashboard/accounts/{account_id}/pnl"
DAILY_URL = "/api/v1/dashboard/accounts/{account_id}/pnl/daily"
PERFORMANCE_URL = "/api/v1/dashboard/accounts/{account_id}/performance"
RISK_URL = "/api/v1/dashboard/accounts/{account_id}/risk"


def _create_user(username: str) -> User:
    user = User.objects.create_user(username=username, password="TestPass123!")
    user.role = Role.VIEWER.value
    user.save()
    return user


def _login(client: APIClient, username: str) -> str:
    response = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": "TestPass123!"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    return response.data["access"]


def _create_key_with_scope(client: APIClient, user: User, scopes: list[str]) -> str:
    client.force_authenticate(user=user)
    response = client.post(
        "/api/v1/auth/api-keys/",
        {"scopes": scopes},
        format="json",
    )
    client.force_authenticate()
    assert response.status_code == status.HTTP_201_CREATED
    return response.data["raw_key"]


class TestJwtCrossAccount:
    def test_own_account_is_readable(self) -> None:
        client = APIClient()
        alice = _create_user("idor-alice-own")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {_login(client, 'idor-alice-own')}")

        for url in (PNL_URL, DAILY_URL, PERFORMANCE_URL, RISK_URL):
            kwargs = {"date_from": "2024-01-01", "date_to": "2024-01-31"} if "daily" in url else {}
            response = client.get(url.format(account_id=alice.id), kwargs)
            assert response.status_code == status.HTTP_200_OK

    def test_other_account_returns_404(self) -> None:
        client = APIClient()
        _create_user("idor-alice-cross")
        bob = _create_user("idor-bob-cross")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {_login(client, 'idor-alice-cross')}")

        for url in (PNL_URL, DAILY_URL, PERFORMANCE_URL, RISK_URL):
            kwargs = {"date_from": "2024-01-01", "date_to": "2024-01-31"} if "daily" in url else {}
            response = client.get(url.format(account_id=bob.id), kwargs)
            assert response.status_code == status.HTTP_404_NOT_FOUND, url

    def test_unauthenticated_returns_401(self) -> None:
        alice = _create_user("idor-alice-anon")
        response = APIClient().get(PNL_URL.format(account_id=alice.id))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestApiKeyCrossAccount:
    def test_key_cannot_read_another_account(self) -> None:
        client = APIClient()
        alice = _create_user("idor-alice-key")
        bob = _create_user("idor-bob-key")
        raw_key = _create_key_with_scope(
            client,
            bob,
            [
                Scope.DASHBOARD_READ_PNL_ANALYTICS.value,
                Scope.DASHBOARD_READ_PERFORMANCE_METRICS.value,
                Scope.DASHBOARD_READ_RISK.value,
            ],
        )
        client.credentials(HTTP_AUTHORIZATION=f"Api-Key {raw_key}")

        for url in (PNL_URL, DAILY_URL, PERFORMANCE_URL, RISK_URL):
            kwargs = {"date_from": "2024-01-01", "date_to": "2024-01-31"} if "daily" in url else {}
            response = client.get(url.format(account_id=alice.id), kwargs)
            assert response.status_code == status.HTTP_404_NOT_FOUND, url

    def test_key_can_read_own_account(self) -> None:
        client = APIClient()
        bob = _create_user("idor-bob-own")
        raw_key = _create_key_with_scope(
            client,
            bob,
            [
                Scope.DASHBOARD_READ_PNL_ANALYTICS.value,
                Scope.DASHBOARD_READ_PERFORMANCE_METRICS.value,
                Scope.DASHBOARD_READ_RISK.value,
            ],
        )
        client.credentials(HTTP_AUTHORIZATION=f"Api-Key {raw_key}")

        for url in (PNL_URL, DAILY_URL, PERFORMANCE_URL, RISK_URL):
            kwargs = {"date_from": "2024-01-01", "date_to": "2024-01-31"} if "daily" in url else {}
            response = client.get(url.format(account_id=bob.id), kwargs)
            assert response.status_code == status.HTTP_200_OK, url