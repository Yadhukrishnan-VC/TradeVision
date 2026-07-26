from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model

from apps.dashboard.infrastructure.trading_core.models import (
    OrderSnapshot,
    PositionSnapshot,
    TradeRecord,
)

pytestmark = pytest.mark.django_db

User = get_user_model()


class TestReconcileTasks:
    def test_reconcile_positions_snapshot(self) -> None:
        from apps.dashboard.tasks.trading_core_tasks import reconcile_positions_snapshot

        account_id = str(uuid.uuid4())
        PositionSnapshot.objects.create(
            position_id=uuid.uuid4(),
            account_id=uuid.UUID(account_id),
            symbol="RELIANCE",
            side="LONG",
            quantity=Decimal("100"),
            entry_price=Decimal("2500.00"),
            is_open=True,
            opened_at=datetime.now(timezone.utc),
        )
        PositionSnapshot.objects.create(
            position_id=uuid.uuid4(),
            account_id=uuid.UUID(account_id),
            symbol="TCS",
            side="LONG",
            quantity=Decimal("50"),
            entry_price=Decimal("3500.00"),
            is_open=True,
            opened_at=datetime.now(timezone.utc),
        )

        result = reconcile_positions_snapshot(account_id)
        assert result["status"] == "completed"
        assert result["open_positions_count"] == 2

    def test_reconcile_open_positions(self) -> None:
        from apps.dashboard.tasks.trading_core_tasks import reconcile_open_positions

        account_id = str(uuid.uuid4())
        PositionSnapshot.objects.create(
            position_id=uuid.uuid4(),
            account_id=uuid.UUID(account_id),
            symbol="RELIANCE",
            side="LONG",
            quantity=Decimal("100"),
            entry_price=Decimal("2500.00"),
            is_open=True,
            opened_at=datetime.now(timezone.utc),
        )

        result = reconcile_open_positions(account_id)
        assert result["status"] == "completed"

    def test_reconcile_orders(self) -> None:
        from apps.dashboard.tasks.trading_core_tasks import reconcile_orders

        account_id = str(uuid.uuid4())
        OrderSnapshot.objects.create(
            order_id=uuid.uuid4(),
            account_id=uuid.UUID(account_id),
            symbol="RELIANCE",
            side="LONG",
            order_type="market",
            status="pending",
            quantity=Decimal("100"),
            filled_quantity=Decimal("0"),
            placed_at=datetime.now(timezone.utc),
        )

        result = reconcile_orders(account_id)
        assert result["status"] == "completed"
        assert result["order_count"] == 1

    def test_reconcile_holdings(self) -> None:
        from apps.dashboard.tasks.trading_core_tasks import reconcile_holdings

        account_id = str(uuid.uuid4())
        from apps.dashboard.infrastructure.trading_core.models import Holding
        Holding.objects.create(
            id=uuid.uuid4(),
            account_id=uuid.UUID(account_id),
            symbol="RELIANCE",
            quantity=Decimal("100"),
            avg_cost=Decimal("2500.00"),
            cost_basis=Decimal("250000.00"),
            opened_at=datetime.now(timezone.utc),
        )

        result = reconcile_holdings(account_id)
        assert result["status"] == "completed"
        assert result["holding_count"] == 1
