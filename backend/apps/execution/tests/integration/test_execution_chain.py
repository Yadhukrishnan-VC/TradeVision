from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

pytestmark = pytest.mark.django_db


def _publish_rule_fired(
    bus,
    *,
    rule_id: str = "long_momentum_v1",
    symbol: str = "RELIANCE",
    entry_price: str = "103.00",
    stop_loss: str = "101.00",
    target_price: str = "110.00",
    analysis_event_id: uuid.UUID | None = None,
) -> tuple[DomainEvent, uuid.UUID]:
    firing_id = analysis_event_id or uuid.uuid4()
    event = DomainEvent.create(
        event_type="rule_engine.RuleFired",
        payload={
            "symbol": symbol,
            "event_type": "BREAKOUT",
            "rule_id": rule_id,
            "severity": "HIGH",
            "trigger_data": {
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "target_price": target_price,
            },
            "analysis_event_id": str(firing_id),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        },
        correlation_id=firing_id,
    )
    bus.publish(event)
    return event, firing_id


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


def _publish_risk_approved(
    bus, *, payload: dict | None = None, correlation_id: uuid.UUID | None = None
) -> DomainEvent:
    event = DomainEvent.create(
        event_type="risk_management.RiskApproved",
        payload=payload if payload is not None else _approved_payload(),
        correlation_id=correlation_id or uuid.uuid4(),
        causation_id=uuid.uuid4(),
    )
    bus.publish(event)
    return event


class TestRiskApprovedToExecutionChain:
    def test_full_chain_rule_fired_to_position(
        self, account, register_risk_handlers, register_dashboard_handlers
    ) -> None:
        from apps.dashboard.infrastructure.trading_core.models import OrderSnapshot
        from apps.execution.infrastructure.models import ExecutionRequest, Order
        from apps.portfolio.infrastructure.models import Position

        bus = get_event_bus()
        register_risk_handlers(bus)
        register_dashboard_handlers(bus)

        fired_event, firing_id = _publish_rule_fired(bus)

        approved = next(
            e for e in bus.published_events if e.event_type == "risk_management.RiskApproved"
        )

        request = ExecutionRequest.objects.get(risk_approved_event_id=approved.event_id)
        assert request.status == "ORDER_CREATED"
        assert request.symbol == "RELIANCE"
        assert request.side == "LONG"
        assert request.account_id == account.id
        assert request.quantity == Decimal("5000")
        assert request.entry_price == Decimal("103.00")
        assert request.correlation_id == firing_id
        assert request.causation_id == fired_event.event_id

        order = Order.objects.get()
        assert order.execution_request_id == request.id
        assert order.status == "FILLED"
        assert order.symbol == "RELIANCE"
        assert order.side == "LONG"
        assert order.order_type == "market"
        assert order.quantity == Decimal("5000")
        assert order.filled_quantity == Decimal("5000")
        assert order.avg_fill_price == Decimal("103.00")
        assert order.broker_name == "paper"
        assert order.correlation_id == firing_id
        assert order.causation_id == fired_event.event_id

        position = Position.objects.get(account_id=account.id, symbol="RELIANCE")
        assert position.side == "LONG"
        assert position.quantity == Decimal("5000")
        assert position.avg_entry_price == Decimal("103.00")

        snapshot = OrderSnapshot.objects.get(order_id=order.id)
        assert snapshot.status == "filled"
        assert snapshot.side == "LONG"
        assert snapshot.symbol == "RELIANCE"
        assert snapshot.filled_quantity == Decimal("5000")
        assert snapshot.account_id == account.id

        placed = next(e for e in bus.published_events if e.event_type == "orders.OrderPlaced")
        assert placed.payload["order_id"] == str(order.id)
        assert placed.payload["account_id"] == str(account.id)
        assert placed.payload["side"] == "LONG"
        assert placed.payload["order_type"] == "market"
        assert placed.payload["quantity"] == "5000"

        filled = next(e for e in bus.published_events if e.event_type == "orders.OrderFilled")
        assert filled.payload["filled_quantity"] == "5000"

        assert not [e for e in bus.published_events if e.event_type == "orders.OrderPartiallyFilled"]
        assert not [e for e in bus.published_events if e.event_type == "orders.OrderRejected"]

    def test_correlation_propagates_through_chain(self, register_risk_handlers) -> None:
        bus = get_event_bus()
        register_risk_handlers(bus)

        _, firing_id = _publish_rule_fired(bus)

        from apps.execution.infrastructure.models import Order

        order = Order.objects.get()
        assert order.correlation_id == firing_id

        placed = next(e for e in bus.published_events if e.event_type == "orders.OrderPlaced")
        filled = next(e for e in bus.published_events if e.event_type == "orders.OrderFilled")
        opened = next(
            e for e in bus.published_events if e.event_type == "positions.PositionOpened"
        )
        assert placed.correlation_id == firing_id
        assert filled.correlation_id == firing_id
        assert opened.correlation_id == firing_id

    def test_duplicate_delivery_via_handler_invocation(
        self, register_risk_handlers
    ) -> None:
        from apps.execution.infrastructure.models import ExecutionRequest, Order
        from apps.risk_management.infrastructure.event_handlers import (
            handle_risk_approved as dispatch,
        )

        bus = get_event_bus()
        register_risk_handlers(bus)

        approved_event = _publish_risk_approved(bus)
        dispatch(approved_event)  # redelivery: same risk_approved_event_id

        assert ExecutionRequest.objects.count() == 1
        assert Order.objects.count() == 1
        placed = [
            e for e in bus.published_events if e.event_type == "orders.OrderPlaced"
        ]
        assert len(placed) == 1

    def test_duplicate_delivery_via_task_retry(self) -> None:
        from apps.execution.infrastructure.models import ExecutionRequest, Order
        from apps.execution.infrastructure.tasks import handle_risk_approved

        risk_approved_event_id = uuid.uuid4()
        correlation_id = uuid.uuid4()
        kwargs = {
            "payload": _approved_payload(),
            "correlation_id": str(correlation_id),
            "causation_id": str(uuid.uuid4()),
            "risk_approved_event_id": str(risk_approved_event_id),
        }

        first = handle_risk_approved.run(**kwargs)
        second = handle_risk_approved.run(**kwargs)  # Celery retry with same args

        assert first["outcome"] == "CREATED"
        assert second["outcome"] == "DUPLICATE"
        assert ExecutionRequest.objects.count() == 1
        assert Order.objects.count() == 1

    def test_duplicate_delivery_via_direct_service_call(self) -> None:
        from apps.execution.application.execution_request_service import (
            ExecutionRequestService,
        )
        from apps.execution.infrastructure.models import ExecutionRequest, Order

        service = ExecutionRequestService()
        risk_approved_event_id = uuid.uuid4()
        correlation_id = uuid.uuid4()

        first = service.intake(
            payload=_approved_payload(),
            correlation_id=correlation_id,
            causation_id=None,
            risk_approved_event_id=risk_approved_event_id,
        )
        second = service.intake(
            payload=_approved_payload(),
            correlation_id=correlation_id,
            causation_id=None,
            risk_approved_event_id=risk_approved_event_id,
        )

        assert first.outcome == "CREATED"
        assert second.outcome == "DUPLICATE"
        assert ExecutionRequest.objects.count() == 1
        assert Order.objects.count() == 1

    def test_risk_rejected_publishes_no_order(self, register_risk_handlers) -> None:
        from apps.execution.infrastructure.models import ExecutionRequest, Order
        from apps.portfolio.infrastructure.models import Position

        bus = get_event_bus()
        register_risk_handlers(bus)

        _publish_rule_fired(bus, stop_loss="103.00")

        rejected = [
            e for e in bus.published_events if e.event_type == "risk_management.RiskRejected"
        ]
        assert len(rejected) == 1
        assert rejected[0].payload["reason_code"] == "STOP_EQUALS_ENTRY"
        assert ExecutionRequest.objects.count() == 0
        assert Order.objects.count() == 0
        assert Position.objects.count() == 0

    def test_kill_switch_active_blocks_order(self, register_risk_handlers) -> None:
        from apps.execution.infrastructure.models import ExecutionRequest, Order
        from apps.portfolio.infrastructure.models import Position
        from apps.risk_management.application.kill_switch_service import (
            KillSwitchService,
        )

        KillSwitchService().activate(scope="GLOBAL", reason="halt")
        bus = get_event_bus()
        register_risk_handlers(bus)

        _publish_rule_fired(bus)

        assert not [e for e in bus.published_events if e.event_type == "risk_management.RiskApproved"]
        assert ExecutionRequest.objects.count() == 0
        assert Order.objects.count() == 0
        assert Position.objects.count() == 0

    def test_insufficient_capital_rejects_without_order(
        self, register_risk_handlers
    ) -> None:
        from apps.execution.infrastructure.models import ExecutionRequest, Order
        from apps.portfolio.infrastructure.models import Position

        bus = get_event_bus()
        register_risk_handlers(bus)

        # notional = 103 * 20000 = 2,060,000 > 1,000,000 funded capital.
        approved_event = _publish_risk_approved(
            bus, payload=_approved_payload(position_size=20000)
        )

        request = ExecutionRequest.objects.get(
            risk_approved_event_id=approved_event.event_id
        )
        assert request.status == "REJECTED_INSUFFICIENT_CAPITAL"
        assert Order.objects.count() == 0
        assert Position.objects.count() == 0
        assert not [e for e in bus.published_events if e.event_type == "orders.OrderPlaced"]

    def test_unknown_rule_rejects_without_order(self, register_risk_handlers) -> None:
        from apps.execution.infrastructure.models import ExecutionRequest, Order

        bus = get_event_bus()
        register_risk_handlers(bus)

        _publish_risk_approved(bus, payload=_approved_payload(rule_id="no_such_rule"))

        assert ExecutionRequest.objects.count() == 0
        assert Order.objects.count() == 0

    def test_market_order_only(self, register_risk_handlers) -> None:
        from apps.execution.infrastructure.models import Order

        bus = get_event_bus()
        register_risk_handlers(bus)
        _publish_rule_fired(bus)

        order = Order.objects.get()
        assert order.order_type == "market"
