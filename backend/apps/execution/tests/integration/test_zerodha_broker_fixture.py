from __future__ import annotations

import json
import pathlib
import uuid
from decimal import Decimal

import pytest

from apps.execution.application.execution_engine import ExecutionEngine
from apps.execution.application.execution_request_service import ExecutionRequestService
from apps.execution.domain.value_objects import OrderPlacementRequest
from apps.execution.infrastructure.brokers.zerodha_broker import ZerodhaBroker
from apps.execution.infrastructure.models import Fill, Order
from apps.portfolio.domain.value_objects import Side

pytestmark = pytest.mark.django_db

FIXTURE_PATH = pathlib.Path(__file__).parent / "fixtures" / "zerodha_sandbox_order_flow.json"


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


def _load_fixture() -> dict:
    with FIXTURE_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


class SandboxReplayClient:
    """Stateful replay of the recorded sandbox fixture.

    The fixture encodes Kite's real response shapes; this client replays them
    and simulates the order lifecycle (OPEN -> COMPLETE / CANCELLED) so the
    adapter and the execution engine can be exercised without live calls.
    """

    def __init__(self, fixture: dict) -> None:
        self._orders: list[dict] = [dict(o) for o in fixture["orders"]]
        self._history: dict[str, list[dict]] = {
            oid: [dict(h) for h in history]
            for oid, history in fixture["history"].items()
        }
        self._place_new = fixture["place_new"]
        self.placed: list[dict] = []
        self.cancel_calls: list[str] = []
        self.access_token_set: str | None = None

    def set_access_token(self, token: str) -> None:
        self.access_token_set = token

    def orders(self) -> list[dict]:
        return [dict(o) for o in self._orders]

    def place_order(self, **kwargs) -> str:
        order = {**self._place_new, **kwargs}
        self._orders.append(order)
        self._history[order["order_id"]] = [
            {
                "order_id": order["order_id"],
                "status": "PENDING",
                "filled_quantity": 0,
            },
            {
                "order_id": order["order_id"],
                "status": "OPEN",
                "filled_quantity": 0,
            },
        ]
        self.placed.append(order)
        return order["order_id"]

    def order_history(self, order_id: str) -> list[dict]:
        return [dict(h) for h in self._history.get(order_id, [])]

    def cancel_order(self, variety: str = "regular", order_id: str = "") -> None:
        self.cancel_calls.append(order_id)
        if order_id in self._history:
            self._history[order_id].append(
                {
                    "order_id": order_id,
                    "status": "CANCELLED",
                    "filled_quantity": 0,
                }
            )


def _sandbox_broker(client: SandboxReplayClient) -> ZerodhaBroker:
    return ZerodhaBroker(
        environment="sandbox",
        client=client,
        api_key="api-key",
        api_secret="api-secret",
        access_token="sandbox-access-token",
    )


class TestZerodhaSandboxFixture:
    def test_fixture_replays_place_status_cancel_lifecycle(self) -> None:
        fixture = _load_fixture()
        client = SandboxReplayClient(fixture)
        broker = _sandbox_broker(client)
        request = OrderPlacementRequest(
            order_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            symbol="RELIANCE",
            side=Side.LONG,
            order_type="market",
            quantity=Decimal("1"),
            price=Decimal("103.00"),
            correlation_id=uuid.uuid4(),
        )

        ack = broker.place_order(request)

        assert ack.broker_order_ref == fixture["place_new"]["order_id"]
        assert client.placed[0]["order_type"] == "LIMIT"
        assert client.placed[0]["tag"] == str(request.correlation_id)
        assert client.access_token_set == "sandbox-access-token"

        opened = broker.get_order_status(ack.broker_order_ref)
        assert opened.status == "OPEN"
        assert opened.filled_quantity == Decimal("0")

        cancelled = broker.cancel_order(ack.broker_order_ref)
        assert cancelled.cancelled is True
        assert client.cancel_calls == [ack.broker_order_ref]

        final = broker.get_order_status(ack.broker_order_ref)
        assert final.status == "CANCELLED"

    def test_fixture_prior_order_does_not_collide_with_new_correlation(self) -> None:
        fixture = _load_fixture()
        client = SandboxReplayClient(fixture)
        broker = _sandbox_broker(client)
        request = OrderPlacementRequest(
            order_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            symbol="TCS",
            side=Side.LONG,
            order_type="market",
            quantity=Decimal("1"),
            price=Decimal("4100.00"),
            correlation_id=uuid.uuid4(),
        )

        ack = broker.place_order(request)

        assert ack.broker_order_ref == fixture["place_new"]["order_id"]
        assert len(client.placed) == 1

    def test_engine_places_order_through_zerodha_sandbox_adapter(self, account) -> None:
        fixture = _load_fixture()
        client = SandboxReplayClient(fixture)
        broker = _sandbox_broker(client)
        order = _make_order(account)

        engine = ExecutionEngine(broker=broker)
        result = engine.execute_order(order.id)

        order.refresh_from_db()
        assert result["status"] == "FILLED"
        assert order.status == "FILLED"
        assert order.broker_order_ref == fixture["place_new"]["order_id"]
        assert order.filled_quantity == order.quantity
        assert Fill.objects.filter(order=order).exists()
        assert client.placed[0]["order_type"] == "LIMIT"
        assert client.placed[0]["tag"]

    def test_engine_marks_order_rejected_via_existing_error_path(self, account) -> None:
        fixture = _load_fixture()

        class _RejectingClient(SandboxReplayClient):
            def place_order(self, **kwargs):
                raise OrderException("Rejected by sandbox: price outside band")

        client = _RejectingClient(fixture)
        broker = _sandbox_broker(client)
        order = _make_order(account)

        engine = ExecutionEngine(broker=broker)
        result = engine.execute_order(order.id)

        order.refresh_from_db()
        assert result["status"] == "REJECTED"
        assert order.status == "REJECTED"
        assert order.filled_quantity == Decimal("0")
        assert not Fill.objects.filter(order=order).exists()


class OrderException(Exception):
    """Fake with the same class name kiteconnect uses for order rejections."""
