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
    OrderSnapshot,
    PositionSnapshot,
    TradeRecord,
)

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def account_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def owner_user(db: Any, account_id: uuid.UUID) -> Any:
    return User.objects.create_user(
        username=f"owner-{uuid.uuid4().hex[:8]}",
        password="SecurePass123!",
    )


@pytest.fixture
def owner_client(api_client: APIClient, owner_user: Any) -> APIClient:
    api_client.force_authenticate(user=owner_user)
    return api_client


class TestDashboardHomeAPI:
    def test_get_summary_authenticated(self, owner_client: APIClient, account_id: uuid.UUID) -> None:
        DashboardHomeSummary.objects.create(
            account_id=account_id,
            open_positions_count=5,
            open_orders_count=3,
            today_realized_pnl=Decimal("15000.00"),
            broker_connection_status="connected",
            market_session_status="open",
        )
        response = owner_client.get("/api/v1/dashboard/home/summary/")
        assert response.status_code == status.HTTP_200_OK

    def test_get_summary_unauthenticated(self, api_client: APIClient) -> None:
        response = api_client.get("/api/v1/dashboard/home/summary/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestPortfolioAPI:
    def test_get_composition_authenticated(self, owner_client: APIClient, account_id: uuid.UUID) -> None:
        from apps.dashboard.infrastructure.trading_core.models import Holding
        Holding.objects.create(
            id=uuid.uuid4(),
            account_id=account_id,
            symbol="RELIANCE",
            quantity=Decimal("100"),
            avg_cost=Decimal("2500.00"),
            cost_basis=Decimal("250000.00"),
            opened_at=datetime.now(timezone.utc),
        )
        response = owner_client.get("/api/v1/dashboard/portfolio/composition/")
        assert response.status_code == status.HTTP_200_OK

    def test_get_composition_unauthenticated(self, api_client: APIClient) -> None:
        response = api_client.get("/api/v1/dashboard/portfolio/composition/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_composition_empty(self, owner_client: APIClient) -> None:
        response = owner_client.get("/api/v1/dashboard/portfolio/composition/")
        assert response.status_code == status.HTTP_200_OK


class TestPositionsAPI:
    def test_list_live_positions(self, owner_client: APIClient, account_id: uuid.UUID) -> None:
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

    def test_list_live_positions_unauthenticated(self, api_client: APIClient) -> None:
        response = api_client.get("/api/v1/dashboard/positions/live/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_position_detail_not_found_returns_404(self, owner_client: APIClient) -> None:
        response = owner_client.get(f"/api/v1/dashboard/positions/live/{uuid.uuid4()}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestOrdersAPI:
    def test_list_orders(self, owner_client: APIClient, account_id: uuid.UUID) -> None:
        OrderSnapshot.objects.create(
            order_id=uuid.uuid4(),
            account_id=account_id,
            symbol="RELIANCE",
            side="LONG",
            order_type="market",
            status="pending",
            quantity=Decimal("100"),
            filled_quantity=Decimal("0"),
            placed_at=datetime.now(timezone.utc),
        )
        response = owner_client.get("/api/v1/dashboard/orders/")
        assert response.status_code == status.HTTP_200_OK

    def test_list_orders_unauthenticated(self, api_client: APIClient) -> None:
        response = api_client.get("/api/v1/dashboard/orders/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_filter_invalid_status_returns_400(self, owner_client: APIClient) -> None:
        response = owner_client.get("/api/v1/dashboard/orders/?status=invalid_status")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestTradeHistoryAPI:
    def test_list_trades(self, owner_client: APIClient, account_id: uuid.UUID) -> None:
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

    def test_list_trades_unauthenticated(self, api_client: APIClient) -> None:
        response = api_client.get("/api/v1/dashboard/trades/history/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestOpenClosedTradesAPI:
    def test_open_trades_alias(self, owner_client: APIClient, account_id: uuid.UUID) -> None:
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
        live_response = owner_client.get("/api/v1/dashboard/positions/live/")
        open_response = owner_client.get("/api/v1/dashboard/trades/open/")
        assert live_response.status_code == status.HTTP_200_OK
        assert open_response.status_code == status.HTTP_200_OK

    def test_closed_trades_alias(self, owner_client: APIClient, account_id: uuid.UUID) -> None:
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
        history_response = owner_client.get("/api/v1/dashboard/trades/history/")
        closed_response = owner_client.get("/api/v1/dashboard/trades/closed/")
        assert history_response.status_code == status.HTTP_200_OK
        assert closed_response.status_code == status.HTTP_200_OK
