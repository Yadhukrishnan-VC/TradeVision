from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.dashboard.infrastructure.trading_core.models import OrderSnapshot
from apps.dashboard.projection.trading_core.order_projection_service import (
    OrderProjectionService,
)
from apps.eventbus.domain.events import DomainEvent

pytestmark = pytest.mark.django_db


class TestOrderProjection:
    def test_order_placed_creates_snapshot(self) -> None:
        account_id = uuid.uuid4()
        order_id = uuid.uuid4()
        event = DomainEvent.create(
            event_type="orders.OrderPlaced",
            payload={
                "account_id": str(account_id),
                "order_id": str(order_id),
                "symbol": "RELIANCE",
                "side": "LONG",
                "order_type": "market",
                "quantity": "100",
            },
            correlation_id=uuid.uuid4(),
        )

        projector = OrderProjectionService()
        projector.handle(event)

        order = OrderSnapshot.objects.get(order_id=order_id)
        assert order.status == "pending"
        assert order.symbol == "RELIANCE"
        assert order.quantity == Decimal("100")

    def test_order_filled_updates_snapshot(self) -> None:
        account_id = uuid.uuid4()
        order_id = uuid.uuid4()

        placed_event = DomainEvent.create(
            event_type="orders.OrderPlaced",
            payload={
                "account_id": str(account_id),
                "order_id": str(order_id),
                "symbol": "RELIANCE",
                "side": "LONG",
                "order_type": "market",
                "quantity": "100",
            },
            correlation_id=uuid.uuid4(),
        )

        filled_event = DomainEvent.create(
            event_type="orders.OrderFilled",
            payload={
                "account_id": str(account_id),
                "order_id": str(order_id),
                "filled_quantity": "100",
                "avg_fill_price": "2500.00",
            },
            correlation_id=uuid.uuid4(),
        )

        projector = OrderProjectionService()
        projector.handle(placed_event)
        projector.handle(filled_event)

        order = OrderSnapshot.objects.get(order_id=order_id)
        assert order.status == "filled"
        assert order.filled_quantity == Decimal("100")
        assert order.avg_fill_price == Decimal("2500.00")

    def test_idempotent_replay_does_not_duplicate(self) -> None:
        account_id = uuid.uuid4()
        order_id = uuid.uuid4()
        event = DomainEvent.create(
            event_type="orders.OrderPlaced",
            payload={
                "account_id": str(account_id),
                "order_id": str(order_id),
                "symbol": "RELIANCE",
                "side": "LONG",
                "order_type": "market",
                "quantity": "100",
            },
            correlation_id=uuid.uuid4(),
        )

        projector = OrderProjectionService()
        projector.handle(event)
        projector.handle(event)

        assert OrderSnapshot.objects.filter(order_id=order_id).count() == 1

    def test_out_of_order_filled_before_placed(self) -> None:
        account_id = uuid.uuid4()
        order_id = uuid.uuid4()

        filled_event = DomainEvent.create(
            event_type="orders.OrderFilled",
            payload={
                "account_id": str(account_id),
                "order_id": str(order_id),
                "filled_quantity": "100",
                "avg_fill_price": "2500.00",
            },
            correlation_id=uuid.uuid4(),
        )

        projector = OrderProjectionService()
        projector.handle(filled_event)

        placed_event = DomainEvent.create(
            event_type="orders.OrderPlaced",
            payload={
                "account_id": str(account_id),
                "order_id": str(order_id),
                "symbol": "RELIANCE",
                "side": "LONG",
                "order_type": "market",
                "quantity": "100",
            },
            correlation_id=uuid.uuid4(),
        )
        projector.handle(placed_event)

        order = OrderSnapshot.objects.get(order_id=order_id)
        assert order.status == "pending"
        assert order.quantity == Decimal("100")
