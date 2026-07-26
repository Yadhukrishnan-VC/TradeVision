from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.dashboard.infrastructure.trading_core.models import TradeRecord
from apps.dashboard.projection.trading_core.trade_projection_service import (
    TradeProjectionService,
)
from apps.eventbus.domain.events import DomainEvent

pytestmark = pytest.mark.django_db


class TestTradeProjection:
    def test_position_closed_creates_trade_record(self) -> None:
        account_id = uuid.uuid4()
        event = DomainEvent.create(
            event_type="positions.PositionClosed",
            payload={
                "account_id": str(account_id),
                "position_id": str(uuid.uuid4()),
                "symbol": "RELIANCE",
                "side": "LONG",
                "entry_price": "2400.00",
                "exit_price": "2600.00",
                "quantity": "100",
                "realized_pnl": "20000.00",
                "realized_pnl_pct": "8.3333",
                "holding_period_seconds": "86400",
            },
            correlation_id=uuid.uuid4(),
        )

        projector = TradeProjectionService()
        projector.handle(event)

        trades = TradeRecord.objects.filter(account_id=account_id)
        assert trades.count() == 1
        assert trades[0].symbol == "RELIANCE"
        assert trades[0].realized_pnl == Decimal("20000.00")

    def test_idempotent_replay_does_not_duplicate(self) -> None:
        account_id = uuid.uuid4()
        event = DomainEvent.create(
            event_type="positions.PositionClosed",
            payload={
                "account_id": str(account_id),
                "position_id": str(uuid.uuid4()),
                "symbol": "RELIANCE",
                "side": "LONG",
                "entry_price": "2400.00",
                "exit_price": "2600.00",
                "quantity": "100",
                "realized_pnl": "20000.00",
                "realized_pnl_pct": "8.3333",
                "holding_period_seconds": "86400",
            },
            correlation_id=uuid.uuid4(),
        )

        projector = TradeProjectionService()
        projector.handle(event)
        projector.handle(event)

        trades = TradeRecord.objects.filter(account_id=account_id)
        assert trades.count() == 1
