from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.dashboard.infrastructure.trading_core.models import (
    DashboardHomeSummary,
    PositionSnapshot,
    TradeRecord,
)

pytestmark = pytest.mark.django_db


class TestContract:
    """Contract tests verify JSON response shape against defined schemas."""

    def test_home_summary_response_shape(self, owner_client: APIClient, account_id: uuid.UUID) -> None:
        DashboardHomeSummary.objects.create(
            account_id=account_id,
            open_positions_count=5,
            open_orders_count=3,
            today_realized_pnl=Decimal("15000.00"),
            today_unrealized_pnl=Decimal("5000.00"),
            active_alerts_count=2,
            broker_connection_status="connected",
            market_session_status="open",
        )
        response = owner_client.get("/api/v1/dashboard/home/summary/")
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        assert "account_id" in data
        assert "open_positions_count" in data
        assert "open_orders_count" in data
        assert "today_realized_pnl" in data
        assert "today_unrealized_pnl" in data
        assert "active_alerts_count" in data
        assert "broker_connection_status" in data
        assert "market_session_status" in data
        assert isinstance(data["open_positions_count"], int)
        assert isinstance(data["broker_connection_status"], str)
        assert data["broker_connection_status"] in ("connected", "degraded", "disconnected")

    def test_trade_record_response_shape(self, owner_client: APIClient, account_id: uuid.UUID) -> None:
        TradeRecord.objects.create(
            trade_id=uuid.uuid4(),
            account_id=account_id,
            symbol="RELIANCE",
            side="LONG",
            entry_price=Decimal("2400.00"),
            exit_price=Decimal("2600.00"),
            quantity=Decimal("100"),
            realized_pnl=Decimal("20000.00"),
            realized_pnl_pct=Decimal("8.3333"),
            opened_at=datetime.now(timezone.utc),
            closed_at=datetime.now(timezone.utc),
            holding_period_seconds=86400,
        )
        response = owner_client.get("/api/v1/dashboard/trades/history/")
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        if isinstance(data, dict) and "results" in data:
            results = data["results"]
        else:
            results = data if isinstance(data, list) else []

        if results:
            trade = results[0]
            assert "trade_id" in trade
            assert "symbol" in trade
            assert "side" in trade
            assert "realized_pnl" in trade
            assert "holding_period_seconds" in trade

    def test_position_response_shape(self, owner_client: APIClient, account_id: uuid.UUID) -> None:
        PositionSnapshot.objects.create(
            position_id=uuid.uuid4(),
            account_id=account_id,
            symbol="RELIANCE",
            side="LONG",
            quantity=Decimal("100"),
            entry_price=Decimal("2500.00"),
            is_open=True,
            opened_at=datetime.now(timezone.utc),
        )
        response = owner_client.get("/api/v1/dashboard/positions/live/")
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        if isinstance(data, dict) and "results" in data:
            results = data["results"]
        else:
            results = data if isinstance(data, list) else []

        if results:
            pos = results[0]
            assert "position_id" in pos
            assert "symbol" in pos
            assert "side" in pos
            assert "quantity" in pos
            assert "entry_price" in pos

    def test_404_problem_detail_shape(self, owner_client: APIClient) -> None:
        response = owner_client.get(f"/api/v1/dashboard/positions/live/{uuid.uuid4()}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

        data = response.data
        assert "type" in data
        assert "title" in data
        assert "status" in data
        assert "instance" in data


@pytest.fixture
def owner_client(api_client: APIClient, owner_user: Any) -> APIClient:
    api_client.force_authenticate(user=owner_user)
    return api_client


@pytest.fixture
def owner_user(db: Any) -> Any:
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(
        username=f"owner-{uuid.uuid4().hex[:8]}",
        password="SecurePass123!",
    )


@pytest.fixture
def account_id() -> uuid.UUID:
    return uuid.uuid4()
