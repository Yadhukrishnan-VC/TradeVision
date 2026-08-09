import uuid
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.execution.domain.value_objects import OrderPlacementRequest, Side
from apps.execution.infrastructure.brokers.paper_broker import PaperBroker
from core.execution_context import bind_backtest_execution


@pytest.mark.django_db
def test_paper_broker_slippage_and_commission():
    # Long order at price 100.00, qty 10
    # Commission 0.001 (10 bps), Slippage 10 bps (0.0010)
    broker = PaperBroker(
        commission_rate=Decimal("0.0010"),
        slippage_bps=Decimal("10.0"),
    )

    req = OrderPlacementRequest(
        order_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        symbol="RELIANCE",
        side=Side.LONG,
        order_type="market",
        quantity=Decimal("10"),
        price=Decimal("100.00"),
        correlation_id=uuid.uuid4(),
    )

    ack = broker.place_order(req)
    plan = broker.get_fill_plan(ack.broker_order_ref)

    assert len(plan) == 1
    fill = plan[0]

    # Fill price for LONG with 10 bps slippage: 100.00 * 1.001 = 100.10
    assert fill.price == Decimal("100.10")
    # Slippage impact: |100.10 - 100.00| * 10 = 1.00
    assert fill.slippage_impact == Decimal("1.00")
    # Commission fee: 10 * 100.10 * 0.0010 = 1.001
    assert fill.commission_fee == Decimal("1.0010")


@pytest.mark.django_db
def test_paper_broker_context_execution_params():
    broker = PaperBroker()

    req = OrderPlacementRequest(
        order_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        symbol="RELIANCE",
        side=Side.LONG,
        order_type="market",
        quantity=Decimal("10"),
        price=Decimal("100.00"),
        correlation_id=uuid.uuid4(),
    )

    with bind_backtest_execution(
        commission_rate=Decimal("0.0005"),
        slippage_bps=Decimal("5.0"),
        next_bar_open=Decimal("102.00"),
    ):
        ack = broker.place_order(req)
        plan = broker.get_fill_plan(ack.broker_order_ref)

    assert len(plan) == 1
    fill = plan[0]

    # Base price taken from next_bar_open: 102.00
    # 5 bps slippage: 102.00 * (1 + 0.0005) = 102.051
    assert fill.price == Decimal("102.051")
    # Commission fee: 10 * 102.051 * 0.0005 = 0.510255
    assert fill.commission_fee == Decimal("0.510255")
