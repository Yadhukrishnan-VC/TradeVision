from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.application.services import APIKeyService
from apps.accounts.domain.value_objects import Scope
from apps.risk_management.infrastructure.models import KillSwitchState

pytestmark = pytest.mark.django_db

DECISIONS_PATH = "/api/v1/risk-management/decisions/"
KILL_SWITCH_PATH = "/api/v1/risk-management/kill-switch/"


def _scoped_client(
    api_client: APIClient,
    user: Any,
    scopes: list[Scope],
) -> APIClient:
    api_key, _ = APIKeyService().create_key(user, scopes)
    api_client.force_authenticate(user=user, token=api_key)
    return api_client


class TestRiskDecisionListAPI:
    def test_list_decisions_requires_scope(
        self, api_client: APIClient, user: Any
    ) -> None:
        _scoped_client(api_client, user, [Scope.READ_MARKET_DATA])

        response = api_client.get(DECISIONS_PATH)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_decisions_empty_with_scope(
        self, api_client: APIClient, user: Any
    ) -> None:
        _scoped_client(api_client, user, [Scope.DASHBOARD_READ_RISK])

        response = api_client.get(DECISIONS_PATH)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {
            "count": 0,
            "next": None,
            "previous": None,
            "results": [],
        }


class TestKillSwitchListAPI:
    def test_list_requires_manage_scope(
        self, api_client: APIClient, user: Any
    ) -> None:
        _scoped_client(api_client, user, [Scope.DASHBOARD_READ_RISK])

        response = api_client.get(KILL_SWITCH_PATH)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_active_states(
        self, api_client: APIClient, user: Any
    ) -> None:
        _scoped_client(api_client, user, [Scope.MANAGE_RISK_POLICY])
        KillSwitchState.objects.create(
            scope="Trading",
            is_active=True,
            reason="test",
            activated_at=datetime.now(timezone.utc),
        )

        response = api_client.get(KILL_SWITCH_PATH)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
