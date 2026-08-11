import uuid
from datetime import datetime
from datetime import timezone as dt_tz
from decimal import Decimal

import pytest

from apps.execution.domain.value_objects import (
    FillMode,
    OrderPlacementRequest,
    OrderStatus,
    Side,
)
from apps.execution.infrastructure.brokers.paper_broker import PaperBroker
from apps.execution.infrastructure.models import Order
from core.clock import bind_simulated_time
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
        quantity=Decimal(10),
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
        quantity=Decimal(10),
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


def _make_intake_order(account_id: uuid.UUID) -> "Order":
    from apps.execution.application.execution_request_service import (
        ExecutionRequestService,
    )
    from apps.execution.infrastructure.models import Order
    from apps.risk_management.domain.events import RiskApproved

    payload = RiskApproved(
        symbol="RELIANCE",
        rule_id="long_momentum_v1",
        event_type="BREAKOUT",
        entry_price=Decimal("103.00"),
        stop_loss=Decimal("100.00"),
        position_size=Decimal(3333),
        risk_amount=Decimal(10000),
        risk_pct_of_capital=Decimal("0.01"),
        risk_reward_ratio=Decimal("3.5"),
        portfolio_gateway_impl="portfolio_v1",
    ).to_payload()
    payload["account_id"] = str(account_id)

    result = ExecutionRequestService().intake(
        payload=payload,
        correlation_id=uuid.uuid4(),
        causation_id=None,
        risk_approved_event_id=uuid.uuid4(),
    )
    assert result.outcome == "CREATED"
    return Order.objects.get(id=result.order_id)


@pytest.mark.django_db
def test_execution_engine_defers_fill_until_next_bar_open(default_account):
    from apps.execution.application.execution_engine import ExecutionEngine
    from apps.execution.infrastructure.models import Fill
    from apps.portfolio.infrastructure.models import (
        AccountCapitalState,
        PositionFillExecution,
    )

    order = _make_intake_order(default_account.id)
    capital = AccountCapitalState.objects.get(account_id=default_account.id)

    # Signal bar: defer_fills=True and no next-bar-open -> ACKNOWLEDGED only.
    with bind_backtest_execution(defer_fills=True):
        engine = ExecutionEngine(broker=PaperBroker(mode=FillMode.FULL_FILL))
        result = engine.execute_order(order.id)

    order.refresh_from_db()
    assert result["status"] == OrderStatus.ACKNOWLEDGED.value
    assert order.status == OrderStatus.ACKNOWLEDGED.value
    assert order.filled_quantity == Decimal(0)
    assert not Fill.objects.filter(order=order).exists()
    assert not PositionFillExecution.objects.filter(
        account_id=default_account.id
    ).exists()
    capital.refresh_from_db()
    assert capital.available_capital == Decimal(1000000)

    # Next bar: the runner re-executes the deferred order on a fresh broker
    # with next_bar_open bound. The deterministic plan is rebuilt against the
    # next bar's real open, never the signal bar's price (no look-ahead fill).
    next_bar_open = Decimal("110.00")
    next_bar_ts = datetime(2024, 6, 10, 6, 0, 0, tzinfo=dt_tz.utc)
    with bind_simulated_time(next_bar_ts), bind_backtest_execution(
        next_bar_open=next_bar_open
    ):
        engine = ExecutionEngine(broker=PaperBroker(mode=FillMode.FULL_FILL))
        result = engine.execute_order(order.id)

    order.refresh_from_db()
    assert result["status"] == OrderStatus.FILLED.value
    assert order.status == OrderStatus.FILLED.value
    assert order.filled_quantity == order.quantity == Decimal(3333)
    assert order.avg_fill_price == Decimal("110.00")

    fill = Fill.objects.get(order=order)
    assert fill.quantity == Decimal(3333)
    assert fill.price == Decimal("110.00")
    assert fill.occurred_at == next_bar_ts

    # The ledger reserves margin at the order's reference entry price.
    capital.refresh_from_db()
    assert capital.available_capital == Decimal(1000000) - (
        Decimal(3333) * Decimal("103.00")
    )
