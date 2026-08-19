from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.execution.domain.exceptions import BrokerRejection, ExecutionDomainError
from apps.execution.domain.value_objects import (
    BrokerAck,
    OrderPlacementRequest,
)
from apps.execution.infrastructure.brokers.zerodha_broker import ZerodhaBroker
from apps.portfolio.domain.value_objects import Side


class OrderException(Exception):
    """Fake with the same class name kiteconnect uses for order rejections."""


class NetworkException(Exception):
    """Fake with the same class name kiteconnect uses for network errors."""


class FakeKiteClient:
    """In-memory double of ``kiteconnect.KiteConnect`` for adapter tests."""

    def __init__(self, *, fail_orders: bool = False) -> None:
        self.access_token_set: str | None = None
        self.session_token: str | None = None
        self._orders: list[dict] = []
        self._history: dict[str, list[dict]] = {}
        self.placed_calls: list[dict] = []
        self.cancel_calls: list[str] = []
        self.fail_orders = fail_orders
        self.routes: dict[str, str] = {}

    def set_access_token(self, token: str) -> None:
        self.access_token_set = token

    def generate_session(self, request_token: str, api_secret: str | None = None) -> dict:
        self.session_token = f"access-{request_token}"
        return {"access_token": self.session_token, "user_id": "AB1234"}

    def orders(self) -> list[dict]:
        if self.fail_orders:
            raise NetworkException("boom: cannot list orders")
        return [dict(o) for o in self._orders]

    def place_order(self, **kwargs) -> str:
        order_id = f"240101{len(self.placed_calls) + 1:08d}"
        order = {"order_id": order_id, **kwargs}
        self.placed_calls.append(order)
        self._orders.append(order)
        self._history[order_id] = [
            dict(order, status="PENDING", filled_quantity=0),
            dict(order, status="OPEN", filled_quantity=0),
        ]
        return order_id

    def order_history(self, order_id: str) -> list[dict]:
        return [dict(h) for h in self._history.get(order_id, [])]

    def cancel_order(self, variety: str = "regular", order_id: str = "") -> None:
        self.cancel_calls.append(order_id)
        if order_id not in self._history:
            return
        self._history[order_id].append(
            dict(self._history[order_id][-1], status="CANCELLED")
        )


def _request(
    *,
    side: Side = Side.LONG,
    symbol: str = "RELIANCE",
    price: Decimal = Decimal("103.00"),
    quantity: Decimal = Decimal("1"),
) -> OrderPlacementRequest:
    return OrderPlacementRequest(
        order_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        symbol=symbol,
        side=side,
        order_type="market",
        quantity=quantity,
        price=price,
        correlation_id=uuid.uuid4(),
    )


def _broker(client: FakeKiteClient, **overrides) -> ZerodhaBroker:
    env = overrides.pop("environment", "sandbox")
    return ZerodhaBroker(
        environment=env,
        client=client,
        api_key="api-key",
        api_secret="api-secret",
        access_token=overrides.pop("access_token", "access-token"),
        request_token=overrides.pop("request_token", None),
        product="MIS",
        **overrides,
    )


class TestPlaceOrder:
    def test_places_limit_order_with_correlation_tag(self) -> None:
        client = FakeKiteClient()
        broker = _broker(client)
        request = _request()

        ack = broker.place_order(request)

        assert isinstance(ack, BrokerAck)
        assert ack.broker_order_ref
        assert len(client.placed_calls) == 1
        placed = client.placed_calls[0]
        assert placed["exchange"] == "NSE"
        assert placed["tradingsymbol"] == "RELIANCE"
        assert placed["transaction_type"] == "BUY"
        assert placed["order_type"] == "LIMIT"
        assert placed["product"] == "MIS"
        assert placed["quantity"] == 1
        assert placed["price"] == float(request.price)
        assert placed["tag"] == str(request.correlation_id)

    def test_short_side_maps_to_sell(self) -> None:
        client = FakeKiteClient()
        broker = _broker(client)

        broker.place_order(_request(side=Side.SHORT))

        assert client.placed_calls[0]["transaction_type"] == "SELL"

    def test_exchange_prefix_is_parsed(self) -> None:
        client = FakeKiteClient()
        broker = _broker(client)

        broker.place_order(_request(symbol="NSE:RELIANCE"))

        assert client.placed_calls[0]["exchange"] == "NSE"
        assert client.placed_calls[0]["tradingsymbol"] == "RELIANCE"

    def test_order_rejection_maps_to_existing_brokerrejection(self) -> None:
        class _RejectingClient(FakeKiteClient):
            def place_order(self, **kwargs):
                raise OrderException("Insufficient margin for this order")

        broker = _broker(_RejectingClient())

        with pytest.raises(BrokerRejection) as excinfo:
            broker.place_order(_request())

        assert excinfo.value.reason_code == "BROKER_REJECTED"
        assert "Insufficient margin" in excinfo.value.reason_message

    def test_network_error_propagates_for_retry(self) -> None:
        class _FlakyClient(FakeKiteClient):
            def place_order(self, **kwargs):
                raise NetworkException("connection reset by peer")

        broker = _broker(_FlakyClient())

        with pytest.raises(NetworkException):
            broker.place_order(_request())

    def test_retried_placement_reuses_existing_order(self) -> None:
        client = FakeKiteClient()
        broker = _broker(client)
        request = _request()

        first = broker.place_order(request)
        second = broker.place_order(request)

        assert second.broker_order_ref == first.broker_order_ref
        assert second.message == "reused existing order (idempotent retry)"
        assert len(client.placed_calls) == 1

    def test_failed_duplicate_check_does_not_place(self) -> None:
        client = FakeKiteClient(fail_orders=True)
        broker = _broker(client)

        with pytest.raises(NetworkException):
            broker.place_order(_request())

        assert client.placed_calls == []


class TestCancelOrder:
    def test_cancel_round_trip(self) -> None:
        client = FakeKiteClient()
        broker = _broker(client)
        ack = broker.place_order(_request())

        result = broker.cancel_order(ack.broker_order_ref)

        assert result.cancelled is True
        assert client.cancel_calls == [ack.broker_order_ref]

    def test_rejection_returns_not_cancelled(self) -> None:
        class _RejectingClient(FakeKiteClient):
            def cancel_order(self, variety: str = "regular", order_id: str = "") -> None:
                raise OrderException("Order already completed")

        broker = _broker(_RejectingClient())

        result = broker.cancel_order("24010100000001")

        assert result.cancelled is False
        assert "Order already completed" in result.message

    def test_network_error_propagates_on_cancel(self) -> None:
        class _FlakyClient(FakeKiteClient):
            def cancel_order(self, variety: str = "regular", order_id: str = "") -> None:
                raise NetworkException("connection reset")

        broker = _broker(_FlakyClient())

        with pytest.raises(NetworkException):
            broker.cancel_order("24010100000001")


class TestGetOrderStatus:
    def test_complete_maps_to_filled(self) -> None:
        client = FakeKiteClient()
        broker = _broker(client)
        ack = broker.place_order(_request(quantity=Decimal("2")))
        client._history[ack.broker_order_ref].append(
            {
                "order_id": ack.broker_order_ref,
                "status": "COMPLETE",
                "filled_quantity": 2,
                "average_price": 103.5,
            }
        )

        status = broker.get_order_status(ack.broker_order_ref)

        assert status.status == "FILLED"
        assert status.filled_quantity == Decimal("2")
        assert status.avg_fill_price == Decimal("103.5")

    def test_open_with_partial_fill_maps_to_partially_filled(self) -> None:
        client = FakeKiteClient()
        broker = _broker(client)
        ack = broker.place_order(_request(quantity=Decimal("10")))
        client._history[ack.broker_order_ref].append(
            {"order_id": ack.broker_order_ref, "status": "OPEN", "filled_quantity": 4}
        )

        status = broker.get_order_status(ack.broker_order_ref)

        assert status.status == "PARTIALLY_FILLED"
        assert status.filled_quantity == Decimal("4")

    def test_rejected_status_passthrough(self) -> None:
        client = FakeKiteClient()
        broker = _broker(client)
        ack = broker.place_order(_request())
        client._history[ack.broker_order_ref].append(
            {"order_id": ack.broker_order_ref, "status": "REJECTED", "filled_quantity": 0}
        )

        assert broker.get_order_status(ack.broker_order_ref).status == "REJECTED"

    def test_unknown_status_defaults_open(self) -> None:
        client = FakeKiteClient()
        broker = _broker(client)
        ack = broker.place_order(_request())
        client._history[ack.broker_order_ref].append(
            {"order_id": ack.broker_order_ref, "status": "MYSTERY", "filled_quantity": 0}
        )

        assert broker.get_order_status(ack.broker_order_ref).status == "OPEN"

    def test_empty_history_returns_unknown(self) -> None:
        broker = _broker(FakeKiteClient())

        status = broker.get_order_status("24010100000099")

        assert status.status == "UNKNOWN"
        assert status.filled_quantity == Decimal("0")
        assert status.avg_fill_price is None


class TestSessionAndSandbox:
    def test_sandbox_route_patch_prefixes_oms_except_instruments(self) -> None:
        client = FakeKiteClient()
        client._routes = {
            "market.instruments.all": "/api/instruments",
            "market.instruments": "/api/instruments",
            "orders.place": "/api/orders/regular",
            "orders.history": "/api/orders/history",
        }

        ZerodhaBroker._patch_sandbox_routes(client)

        assert client._routes["orders.place"] == "/oms/api/orders/regular"
        assert client._routes["orders.history"] == "/oms/api/orders/history"
        assert client._routes["market.instruments.all"] == "/api/instruments"

    def test_request_token_is_exchanged_for_access_token(self) -> None:
        client = FakeKiteClient()
        broker = _broker(client, access_token=None, request_token="RT-123")

        broker._get_client()

        assert client.session_token == "access-RT-123"
        assert client.access_token_set == "access-RT-123"

    def test_missing_access_token_raises_explicit_error(self) -> None:
        broker = _broker(FakeKiteClient(), access_token=None, request_token=None)

        with pytest.raises(ExecutionDomainError) as excinfo:
            broker._get_client()

        assert excinfo.value.code == "NO_ZERODHA_ACCESS_TOKEN"

    def test_live_environment_is_refused(self) -> None:
        # Default test settings: ALGO_REGISTRATION_ID is empty -> the
        # registration gate fires first.
        with pytest.raises(ExecutionDomainError) as excinfo:
            _broker(FakeKiteClient(), environment="live")

        assert excinfo.value.code == "LIVE_UNREACHABLE_NO_ALGO_REGISTRATION"

    def test_live_environment_with_registration_still_refused(self, settings) -> None:
        # Even with ALGO_REGISTRATION_ID recorded, live is unreachable until
        # the Phase 2 explicit unlock (ADR-030) exists.
        settings.ALGO_REGISTRATION_ID = "SEBI-ALGO-12345"
        with pytest.raises(ExecutionDomainError) as excinfo:
            _broker(FakeKiteClient(), environment="live")

        assert excinfo.value.code == "LIVE_UNREACHABLE_PHASE_1"
