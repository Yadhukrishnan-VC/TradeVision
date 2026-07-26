from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.dashboard.infrastructure.trading_core.models import DashboardHomeSummary
from apps.dashboard.projection.trading_core.portfolio_summary_projection_service import (
    PortfolioSummaryProjectionService,
)
from apps.eventbus.domain.events import DomainEvent

pytestmark = pytest.mark.django_db


class TestPortfolioSummaryProjection:
    def test_position_opened_increments_count(self) -> None:
        account_id = uuid.uuid4()
        event = DomainEvent.create(
            event_type="positions.PositionOpened",
            payload={
                "account_id": str(account_id),
                "position_id": str(uuid.uuid4()),
                "symbol": "RELIANCE",
                "side": "LONG",
                "quantity": "100",
                "entry_price": "2500.00",
            },
            correlation_id=uuid.uuid4(),
        )

        projector = PortfolioSummaryProjectionService()
        projector.handle(event)

        summary = DashboardHomeSummary.objects.get(pk=account_id)
        assert summary.open_positions_count == 1

    def test_position_closed_decrements_count(self) -> None:
        account_id = uuid.uuid4()

        open_event = DomainEvent.create(
            event_type="positions.PositionOpened",
            payload={
                "account_id": str(account_id),
                "position_id": str(uuid.uuid4()),
                "symbol": "RELIANCE",
                "side": "LONG",
                "quantity": "100",
                "entry_price": "2500.00",
            },
            correlation_id=uuid.uuid4(),
        )

        close_event = DomainEvent.create(
            event_type="positions.PositionClosed",
            payload={
                "account_id": str(account_id),
                "position_id": str(uuid.uuid4()),
                "symbol": "RELIANCE",
                "side": "LONG",
                "quantity": "100",
            },
            correlation_id=uuid.uuid4(),
        )

        projector = PortfolioSummaryProjectionService()
        projector.handle(open_event)
        projector.handle(close_event)

        summary = DashboardHomeSummary.objects.get(pk=account_id)
        assert summary.open_positions_count == 0

    def test_order_placed_increments_open_orders(self) -> None:
        account_id = uuid.uuid4()
        event = DomainEvent.create(
            event_type="orders.OrderPlaced",
            payload={
                "account_id": str(account_id),
                "order_id": str(uuid.uuid4()),
                "symbol": "RELIANCE",
                "side": "LONG",
                "order_type": "market",
                "quantity": "100",
            },
            correlation_id=uuid.uuid4(),
        )

        projector = PortfolioSummaryProjectionService()
        projector.handle(event)

        summary = DashboardHomeSummary.objects.get(pk=account_id)
        assert summary.open_orders_count == 1

    def test_broker_status_changed(self) -> None:
        account_id = uuid.uuid4()
        event = DomainEvent.create(
            event_type="broker.ConnectionStatusChanged",
            payload={
                "account_id": str(account_id),
                "status": "connected",
            },
            correlation_id=uuid.uuid4(),
        )

        projector = PortfolioSummaryProjectionService()
        projector.handle(event)

        summary = DashboardHomeSummary.objects.get(pk=account_id)
        assert summary.broker_connection_status == "connected"

    def test_idempotent_replay(self) -> None:
        account_id = uuid.uuid4()
        event = DomainEvent.create(
            event_type="positions.PositionOpened",
            payload={
                "account_id": str(account_id),
                "position_id": str(uuid.uuid4()),
                "symbol": "RELIANCE",
                "side": "LONG",
                "quantity": "100",
                "entry_price": "2500.00",
            },
            correlation_id=uuid.uuid4(),
        )

        projector = PortfolioSummaryProjectionService()
        projector.handle(event)
        projector.handle(event)

        summary = DashboardHomeSummary.objects.get(pk=account_id)
        assert summary.open_positions_count == 1
