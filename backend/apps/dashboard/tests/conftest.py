from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.dashboard.infrastructure.trading_core.models import (
    DashboardHomeSummary,
    Holding,
    OrderSnapshot,
    PositionSnapshot,
    TradeRecord,
)
from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus

User = get_user_model()


@pytest.fixture(autouse=True)
def _reset_bus() -> Generator[None, None, None]:
    reset_event_bus()
    yield
    reset_event_bus()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def authenticated_client(api_client: APIClient, user: Any) -> APIClient:
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def user(db: Any) -> Any:
    return User.objects.create_user(
        username=f"trader-{uuid.uuid4().hex[:8]}",
        password="SecurePass123!",
    )


@pytest.fixture
def account_id(user: Any) -> uuid.UUID:
    return uuid.UUID(int=user.id + 1000000)


@pytest.fixture
def sample_position(db: Any, account_id: uuid.UUID) -> PositionSnapshot:
    return PositionSnapshot.objects.create(
        position_id=uuid.uuid4(),
        account_id=account_id,
        symbol="RELIANCE",
        side="LONG",
        quantity=Decimal("100"),
        entry_price=Decimal("2500.00"),
        is_open=True,
        opened_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_order(db: Any, account_id: uuid.UUID) -> OrderSnapshot:
    return OrderSnapshot.objects.create(
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


@pytest.fixture
def sample_trade(db: Any, account_id: uuid.UUID) -> TradeRecord:
    return TradeRecord.objects.create(
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


@pytest.fixture
def sample_holding(db: Any, account_id: uuid.UUID) -> Holding:
    return Holding.objects.create(
        id=uuid.uuid4(),
        account_id=account_id,
        symbol="RELIANCE",
        quantity=Decimal("100"),
        avg_cost=Decimal("2500.00"),
        cost_basis=Decimal("250000.00"),
        opened_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_home_summary(db: Any, account_id: uuid.UUID) -> DashboardHomeSummary:
    return DashboardHomeSummary.objects.create(
        account_id=account_id,
        open_positions_count=5,
        open_orders_count=3,
        today_realized_pnl=Decimal("15000.00"),
        today_unrealized_pnl=Decimal("5000.00"),
        active_alerts_count=2,
        broker_connection_status="connected",
        market_session_status="open",
    )


@pytest.fixture
def sample_event() -> DomainEvent:
    return DomainEvent.create(
        event_type="positions.PositionOpened",
        payload={
            "account_id": str(uuid.uuid4()),
            "position_id": str(uuid.uuid4()),
            "symbol": "RELIANCE",
            "side": "LONG",
            "quantity": "100",
            "entry_price": "2500.00",
        },
        correlation_id=uuid.uuid4(),
    )


@pytest.fixture
def correlation_id() -> str:
    return str(uuid.uuid4())
