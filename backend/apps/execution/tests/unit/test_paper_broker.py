from __future__ import annotations

import inspect
import uuid
from decimal import Decimal

import pytest

from apps.execution.domain.exceptions import BrokerRejection
from apps.execution.domain.value_objects import (
    FillMode,
    OrderPlacementRequest,
    OrderType,
)
from apps.execution.infrastructure.brokers.paper_broker import PaperBroker
from apps.portfolio.domain.value_objects import Side


def _request(*, quantity: str = "5000", price: str = "103.00") -> OrderPlacementRequest:
    return OrderPlacementRequest(
        order_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        symbol="RELIANCE",
        side=Side.LONG,
        order_type=OrderType.MARKET.value,
        quantity=Decimal(quantity),
        price=Decimal(price),
        correlation_id=uuid.uuid4(),
    )


class TestPaperBrokerModes:
    def test_full_fill_single_deterministic_fill(self) -> None:
        broker = PaperBroker(FillMode.FULL_FILL)
        ack = broker.place_order(_request())
        plan = broker.get_fill_plan(ack.broker_order_ref)
        assert len(plan) == 1
        assert plan[0].sequence == 1
        assert plan[0].quantity == Decimal("5000")
        assert plan[0].price == Decimal("103.00")

    def test_partial_then_fill_is_fixed_60_40(self) -> None:
        broker = PaperBroker(FillMode.PARTIAL_THEN_FILL)
        ack = broker.place_order(_request())
        plan = broker.get_fill_plan(ack.broker_order_ref)
        assert [f.sequence for f in plan] == [1, 2]
        assert plan[0].quantity == Decimal("3000")
        assert plan[1].quantity == Decimal("2000")
        assert plan[0].price == plan[1].price == Decimal("103.00")

    def test_partial_plan_sums_to_order_quantity(self) -> None:
        broker = PaperBroker(FillMode.PARTIAL_THEN_FILL)
        ack = broker.place_order(_request(quantity="10000"))
        plan = broker.get_fill_plan(ack.broker_order_ref)
        assert sum((f.quantity for f in plan), Decimal("0")) == Decimal("10000")

    def test_reject_mode_raises_broker_rejection(self) -> None:
        broker = PaperBroker(FillMode.REJECT)
        with pytest.raises(BrokerRejection) as exc:
            broker.place_order(_request())
        assert exc.value.reason_code == "BROKER_REJECTED"

    def test_no_fill_expire_has_empty_plan(self) -> None:
        broker = PaperBroker(FillMode.NO_FILL_EXPIRE)
        ack = broker.place_order(_request())
        assert broker.get_fill_plan(ack.broker_order_ref) == []

    def test_cancel_then_status(self) -> None:
        broker = PaperBroker(FillMode.NO_FILL_EXPIRE)
        ack = broker.place_order(_request())
        result = broker.cancel_order(ack.broker_order_ref)
        assert result.cancelled is True
        assert broker.get_order_status(ack.broker_order_ref).status == "CANCELLED"

    def test_unknown_ref_returns_empty(self) -> None:
        broker = PaperBroker(FillMode.FULL_FILL)
        assert broker.get_fill_plan("does-not-exist") == []
        assert broker.get_order_status("does-not-exist").status == "UNKNOWN"


class TestPaperBrokerIsolation:
    def test_module_has_no_network_dependencies(self) -> None:
        module = inspect.getsource(__import__(
            "apps.execution.infrastructure.brokers.paper_broker", fromlist=["PaperBroker"]
        ))
        for forbidden in ("httpx", "requests", "urllib", "socket", "kiteconnect", "zerodha"):
            assert forbidden not in module

    def test_placed_order_uses_request_price_unless_overridden(self) -> None:
        broker = PaperBroker(FillMode.FULL_FILL, fill_price=Decimal("99.50"))
        ack = broker.place_order(_request())
        plan = broker.get_fill_plan(ack.broker_order_ref)
        assert plan[0].price == Decimal("99.50")
