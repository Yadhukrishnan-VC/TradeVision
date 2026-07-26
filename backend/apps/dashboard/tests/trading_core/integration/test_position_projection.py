from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from apps.dashboard.infrastructure.common.event_log import EventLog
from apps.dashboard.infrastructure.trading_core.models import PositionSnapshot
from apps.dashboard.projection.trading_core.position_projection_service import (
    PositionProjectionService,
)
from apps.eventbus.domain.events import DomainEvent

pytestmark = pytest.mark.django_db


class TestPositionProjection:
    def test_position_opened_creates_snapshot(self) -> None:
        account_id = uuid.uuid4()
        position_id = uuid.uuid4()
        event = DomainEvent.create(
            event_type="positions.PositionOpened",
            payload={
                "account_id": str(account_id),
                "position_id": str(position_id),
                "symbol": "RELIANCE",
                "side": "LONG",
                "quantity": "100",
                "entry_price": "2500.00",
            },
            correlation_id=uuid.uuid4(),
        )

        projector = PositionProjectionService()
        projector.handle(event)

        position = PositionSnapshot.objects.get(position_id=position_id)
        assert position.symbol == "RELIANCE"
        assert position.side == "LONG"
        assert position.quantity == Decimal("100")
        assert position.entry_price == Decimal("2500.00")
        assert position.is_open is True

    def test_idempotent_replay_does_not_duplicate(self) -> None:
        account_id = uuid.uuid4()
        position_id = uuid.uuid4()
        event = DomainEvent.create(
            event_type="positions.PositionOpened",
            payload={
                "account_id": str(account_id),
                "position_id": str(position_id),
                "symbol": "RELIANCE",
                "side": "LONG",
                "quantity": "100",
                "entry_price": "2500.00",
            },
            correlation_id=uuid.uuid4(),
        )

        projector = PositionProjectionService()
        projector.handle(event)
        projector.handle(event)

        assert PositionSnapshot.objects.filter(position_id=position_id).count() == 1
        assert EventLog.objects.filter(
            event_id=event.event_id, projector="position_projector"
        ).count() == 1

    def test_position_closed_updates_snapshot(self) -> None:
        account_id = uuid.uuid4()
        position_id = uuid.uuid4()

        open_event = DomainEvent.create(
            event_type="positions.PositionOpened",
            payload={
                "account_id": str(account_id),
                "position_id": str(position_id),
                "symbol": "RELIANCE",
                "side": "LONG",
                "quantity": "100",
                "entry_price": "2500.00",
            },
            correlation_id=uuid.uuid4(),
        )

        closed_event = DomainEvent.create(
            event_type="positions.PositionClosed",
            payload={
                "account_id": str(account_id),
                "position_id": str(position_id),
                "symbol": "RELIANCE",
                "side": "LONG",
                "quantity": "100",
            },
            correlation_id=uuid.uuid4(),
        )

        projector = PositionProjectionService()
        projector.handle(open_event)
        projector.handle(closed_event)

        position = PositionSnapshot.objects.get(position_id=position_id)
        assert position.is_open is False
        assert position.closed_at is not None

    def test_position_quantity_changed(self) -> None:
        account_id = uuid.uuid4()
        position_id = uuid.uuid4()

        open_event = DomainEvent.create(
            event_type="positions.PositionOpened",
            payload={
                "account_id": str(account_id),
                "position_id": str(position_id),
                "symbol": "RELIANCE",
                "side": "LONG",
                "quantity": "100",
                "entry_price": "2500.00",
            },
            correlation_id=uuid.uuid4(),
        )

        qty_event = DomainEvent.create(
            event_type="positions.PositionQuantityChanged",
            payload={
                "account_id": str(account_id),
                "position_id": str(position_id),
                "quantity": "50",
            },
            correlation_id=uuid.uuid4(),
        )

        projector = PositionProjectionService()
        projector.handle(open_event)
        projector.handle(qty_event)

        position = PositionSnapshot.objects.get(position_id=position_id)
        assert position.quantity == Decimal("50")
