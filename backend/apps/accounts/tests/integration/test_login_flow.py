from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.domain.value_objects import Role

pytestmark = pytest.mark.django_db

User = get_user_model()


class TestLoginFlow:
    def test_login_success(self, api_client: APIClient) -> None:
        User.objects.create_user(username="testuser", password="TestPass123!")
        response = api_client.post(
            "/api/v1/auth/login/",
            {"username": "testuser", "password": "TestPass123!"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data
        assert "user" in response.data

    def test_login_invalid_credentials(self, api_client: APIClient) -> None:
        response = api_client.post(
            "/api/v1/auth/login/",
            {"username": "nonexistent", "password": "wrong"},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_missing_fields(self, api_client: APIClient) -> None:
        response = api_client.post(
            "/api/v1/auth/login/",
            {},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_me_endpoint_with_token(self, api_client: APIClient) -> None:
        user = User.objects.create_user(username="testuser", password="TestPass123!")
        api_client.force_authenticate(user=user)
        response = api_client.get("/api/v1/auth/me/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["username"] == "testuser"

    def test_me_endpoint_unauthenticated(self, api_client: APIClient) -> None:
        response = api_client.get("/api/v1/auth/me/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_token_refresh(self, api_client: APIClient) -> None:
        from rest_framework_simplejwt.tokens import RefreshToken
        user = User.objects.create_user(username="testuser", password="TestPass123!")
        refresh = RefreshToken.for_user(user)

        response = api_client.post(
            "/api/v1/auth/refresh/",
            {"refresh": str(refresh)},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
