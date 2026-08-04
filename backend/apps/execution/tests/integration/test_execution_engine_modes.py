from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.execution.application.execution_engine import ExecutionEngine
from apps.execution.application.execution_request_service import ExecutionRequestService
from apps.execution.domain.value_objects import FillMode
from apps.execution.infrastructure.brokers.paper_broker import PaperBroker
from apps.execution.infrastructure.models import ExecutionRequest, Fill, Order

pytestmark = pytest.mark.django_db


def _approved_payload(**overrides: object) -> dict:
    from apps.risk_management.domain.events import RiskApproved

    base = RiskApproved(
        symbol="RELIANCE",
        rule_id="long_momentum_v1",
        event_type="BREAKOUT",
        entry_price=Decimal("103.00"),
        stop_loss=Decimal("101.00"),
        position_size=5000,
        risk_amount=Decimal("10000"),
        risk_pct_of_capital=Decimal("0.01"),
        risk_reward_ratio=Decimal("3.5"),
        portfolio_gateway_impl="portfolio_v1",
    )
    payload = base.to_payload()
    payload.update({k: v for k, v in overrides.items()})
    return payload


def _make_order(account) -> Order:
    service = ExecutionRequestService()
    result = service.intake(
        payload=_approved_payload(),
        correlation_id=uuid.uuid4(),
        causation_id=None,
        risk_approved_event_id=uuid.uuid4(),
    )
    assert result.outcome == "CREATED"
    return Order.objects.get(id=result.order_id)


class TestExecutionEngineModes:
    def test_reject_mode(self, account, register_dashboard_handlers) -> None:
        from apps.dashboard.infrastructure.trading_core.models import OrderSnapshot

        bus = get_event_bus()
        register_dashboard_handlers(bus)
        order = _make_order(account)
        engine = ExecutionEngine(broker=PaperBroker(FillMode.REJECT))

        result = engine.execute_order(order.id)

        order.refresh_from_db()
        assert result["status"] == "REJECTED"
        assert order.status == "REJECTED"
        assert order.filled_quantity == Decimal("0")
        assert not Fill.objects.filter(order=order).exists()

        rejected = next(
            e for e in bus.published_events if e.event_type == "orders.OrderRejected"
        )
        assert rejected.payload["reason_code"] == "BROKER_REJECTED"
        assert rejected.payload["reason_message"]
        assert not [e for e in bus.published_events if e.event_type == "orders.OrderPlaced"]

        assert not OrderSnapshot.objects.filter(order_id=order.id).exists()

    def test_partial_then_fill_60_40(self, account, register_dashboard_handlers) -> None:
        from apps.dashboard.infrastructure.trading_core.models import OrderSnapshot
        from apps.portfolio.infrastructure.models import Position

        bus = get_event_bus()
        register_dashboard_handlers(bus)
        order = _make_order(account)
        engine = ExecutionEngine(broker=PaperBroker(FillMode.PARTIAL_THEN_FILL))

        result = engine.execute_order(order.id)

        order.refresh_from_db()
        assert result["status"] == "FILLED"
        assert order.status == "FILLED"
        assert order.filled_quantity == order.quantity

        fills = list(Fill.objects.filter(order=order).order_by("sequence"))
        assert [f.sequence for f in fills] == [1, 2]
        assert fills[0].quantity == Decimal("3000")
        assert fills[1].quantity == Decimal("2000")
        assert fills[0].price == fills[1].price == Decimal("103.00")

        partial = next(
            e for e in bus.published_events if e.event_type == "orders.OrderPartiallyFilled"
        )
        assert partial.payload["filled_quantity"] == "3000"
        filled = next(
            e for e in bus.published_events if e.event_type == "orders.OrderFilled"
        )
        assert filled.payload["filled_quantity"] == "5000"

        position = Position.objects.get(account_id=account.id, symbol="RELIANCE")
        assert position.quantity == Decimal("5000")
        assert position.side == "LONG"

        snapshot = OrderSnapshot.objects.get(order_id=order.id)
        assert snapshot.status == "filled"
        assert snapshot.filled_quantity == Decimal("5000")

    def test_no_fill_expire(self, account, register_dashboard_handlers) -> None:
        from apps.dashboard.infrastructure.trading_core.models import OrderSnapshot
        from apps.portfolio.infrastructure.models import Position

        bus = get_event_bus()
        register_dashboard_handlers(bus)
        order = _make_order(account)
        engine = ExecutionEngine(broker=PaperBroker(FillMode.NO_FILL_EXPIRE))

        result = engine.execute_order(order.id)

        order.refresh_from_db()
        assert result["status"] == "EXPIRED"
        assert order.status == "EXPIRED"
        assert not Fill.objects.filter(order=order).exists()
        assert not Position.objects.filter(account_id=account.id, symbol="RELIANCE").exists()

        assert next(
            e for e in bus.published_events if e.event_type == "orders.OrderExpired"
        )
        assert not [e for e in bus.published_events if e.event_type == "orders.OrderFilled"]

        snapshot = OrderSnapshot.objects.get(order_id=order.id)
        assert snapshot.status == "expired"

    def test_redelivery_is_idempotent(self, account) -> None:
        from apps.portfolio.infrastructure.models import Position

        bus = get_event_bus()
        order = _make_order(account)
        engine = ExecutionEngine(broker=PaperBroker(FillMode.PARTIAL_THEN_FILL))

        engine.execute_order(order.id)
        fills_before = Fill.objects.filter(order=order).count()
        filled_events_before = len(
            [e for e in bus.published_events if e.event_type == "orders.OrderFilled"]
        )

        # Simulated redelivery of the process_order task.
        engine.execute_order(order.id)

        order.refresh_from_db()
        assert order.status == "FILLED"
        assert Fill.objects.filter(order=order).count() == fills_before == 2
        assert len(
            [e for e in bus.published_events if e.event_type == "orders.OrderFilled"]
        ) == filled_events_before
        position = Position.objects.get(account_id=account.id, symbol="RELIANCE")
        assert position.quantity == Decimal("5000")

    def test_unknown_order_id_returns_missing(self) -> None:
        engine = ExecutionEngine(broker=PaperBroker(FillMode.FULL_FILL))
        result = engine.execute_order(uuid.uuid4())
        assert result["status"] == "MISSING"


class TestExecutionRequestIntake:
    def test_short_rule_derives_short_side(self, account) -> None:
        service = ExecutionRequestService()
        result = service.intake(
            payload=_approved_payload(rule_id="short_sell_v1"),
            correlation_id=uuid.uuid4(),
            causation_id=None,
            risk_approved_event_id=uuid.uuid4(),
        )
        assert result.outcome == "CREATED"
        request = ExecutionRequest.objects.get(id=result.request_id)
        assert request.side == "SHORT"

    def test_insufficient_capital_outcome(self, account) -> None:
        service = ExecutionRequestService()
        result = service.intake(
            payload=_approved_payload(position_size=20000),
            correlation_id=uuid.uuid4(),
            causation_id=None,
            risk_approved_event_id=uuid.uuid4(),
        )
        assert result.outcome == "REJECTED_INSUFFICIENT_CAPITAL"
        assert result.order_id is None
        request = ExecutionRequest.objects.get(id=result.request_id)
        assert request.status == "REJECTED_INSUFFICIENT_CAPITAL"
        assert "Available capital" in request.reason_message
