from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from apps.dashboard.infrastructure.trading_core.models import (
    DashboardHomeSummary,
    PositionSnapshot,
)

pytestmark = pytest.mark.django_db

User = get_user_model()


class TestLoad:
    """Basic load/smoke tests for API endpoints."""

    def test_concurrent_get_home_summary(self, api_client: APIClient) -> None:
        user = User.objects.create_user(
            username=f"load-{uuid.uuid4().hex[:8]}",
            password="SecurePass123!",
        )
        account_id = uuid.uuid4()
        DashboardHomeSummary.objects.create(
            account_id=account_id,
            open_positions_count=10,
            broker_connection_status="connected",
            market_session_status="open",
        )
        api_client.force_authenticate(user=user)

        responses = []
        for _ in range(10):
            response = api_client.get("/api/v1/dashboard/home/summary/")
            responses.append(response)

        assert all(r.status_code == status.HTTP_200_OK for r in responses)

    def test_concurrent_list_positions(self, api_client: APIClient) -> None:
        user = User.objects.create_user(
            username=f"load-{uuid.uuid4().hex[:8]}",
            password="SecurePass123!",
        )
        account_id = uuid.uuid4()

        for i in range(5):
            PositionSnapshot.objects.create(
                position_id=uuid.uuid4(),
                account_id=account_id,
                symbol=f"SYM{i}",
                side="LONG",
                quantity=Decimal("100"),
                entry_price=Decimal("2500.00"),
                is_open=True,
                opened_at=datetime.now(timezone.utc),
            )

        api_client.force_authenticate(user=user)

        responses = []
        for _ in range(10):
            response = api_client.get("/api/v1/dashboard/positions/live/")
            responses.append(response)

        assert all(r.status_code == status.HTTP_200_OK for r in responses)
        assert len(responses[0].data.get("results", responses[0].data)) == 5
