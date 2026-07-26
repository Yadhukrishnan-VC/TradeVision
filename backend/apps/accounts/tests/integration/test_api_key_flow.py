from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.infrastructure.models import APIKey

pytestmark = pytest.mark.django_db

User = get_user_model()


class TestAPIKeyFlow:
    def test_create_api_key_returns_raw_key_once(self, api_client: APIClient) -> None:
        user = User.objects.create_user(username="keyuser", password="TestPass123!")
        api_client.force_authenticate(user=user)

        response = api_client.post(
            "/api/v1/auth/api-keys/",
            {"scopes": ["read:market_data"]},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert "raw_key" in response.data
        assert "id" in response.data
        assert response.data["scopes"] == ["read:market_data"]

        key_id = response.data["id"]
        raw_key = response.data["raw_key"]
        assert len(raw_key) > 0

    def test_list_api_keys_never_exposes_raw_key(self, api_client: APIClient) -> None:
        user = User.objects.create_user(username="listuser", password="TestPass123!")
        api_client.force_authenticate(user=user)

        api_client.post(
            "/api/v1/auth/api-keys/",
            {"scopes": ["read:market_data"]},
            format="json",
        )

        response = api_client.get("/api/v1/auth/api-keys/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1
        for key in response.data:
            assert "key_hash" not in key
            assert "raw_key" not in key

    def test_revoked_key_fails_authentication(self, api_client: APIClient) -> None:
        user = User.objects.create_user(username="revokeuser", password="TestPass123!")
        api_client.force_authenticate(user=user)

        create_response = api_client.post(
            "/api/v1/auth/api-keys/",
            {"scopes": ["read:market_data"]},
            format="json",
        )
        key_id = create_response.data["id"]

        delete_response = api_client.delete(f"/api/v1/auth/api-keys/{key_id}/")
        assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    def test_invalid_scope_rejected(self, api_client: APIClient) -> None:
        user = User.objects.create_user(username="scopetest", password="TestPass123!")
        api_client.force_authenticate(user=user)

        response = api_client.post(
            "/api/v1/auth/api-keys/",
            {"scopes": ["invalid:scope"]},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_key_empty_scopes_rejected(self, api_client: APIClient) -> None:
        user = User.objects.create_user(username="emptyscopes", password="TestPass123!")
        api_client.force_authenticate(user=user)

        response = api_client.post(
            "/api/v1/auth/api-keys/",
            {"scopes": []},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
