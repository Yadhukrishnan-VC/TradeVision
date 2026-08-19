"""WS3 — trading-core WebSocket consumer production tests.

Covers authentication rejection, per-user group isolation, live event
delivery for every consumer, bulk snapshot emission, arbitrary client
frames, and disconnect cleanup.
"""

from __future__ import annotations

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model

from apps.dashboard.tests.websocket.conftest import (
    TRADING_CORE_APPS,
    WSClient,
    build_scope,
)

User = get_user_model()


def _client(name: str, *, user, path: str) -> WSClient:
    return WSClient(TRADING_CORE_APPS[name], build_scope(user=user, path=path))


class TestAuthentication:
    def test_consumers_reject_missing_user(self) -> None:
        async def scenario() -> None:
            for name in TRADING_CORE_APPS:
                client = _client(name, user=None, path=f"/ws/dashboard/{name}/")
                connected, close = await client.connect()
                assert connected is False
                assert close is not None and close.get("code") == 4029
                await client.disconnect()

        async_to_sync(scenario)()

    def test_consumers_reject_anonymous_user(self, anonymous_user) -> None:
        async def scenario() -> None:
            for name in TRADING_CORE_APPS:
                client = _client(
                    name, user=anonymous_user, path=f"/ws/dashboard/{name}/"
                )
                connected, close = await client.connect()
                assert connected is False
                assert close is not None and close.get("code") == 4029
                await client.disconnect()

        async_to_sync(scenario)()


class TestConnectAndDelivery:
    def test_home_consumer_connects_and_receives_update(
        self, new_user, channel_layer
    ) -> None:
        async def scenario() -> None:
            client = _client("home", user=new_user, path="/ws/dashboard/home/")
            connected, _ = await client.connect()
            assert connected is True

            await channel_layer.group_send(
                f"dashboard.home.{new_user.id}",
                {"type": "home_summary_updated", "data": {"cash": "123.45"}},
            )
            await client.wait()
            assert {"cash": "123.45"} in client.sent_json_list()
            await client.disconnect()

        async_to_sync(scenario)()

    def test_portfolio_consumer_receives_update(self, new_user, channel_layer) -> None:
        async def scenario() -> None:
            client = _client(
                "portfolio", user=new_user, path="/ws/dashboard/portfolio/"
            )
            connected, _ = await client.connect()
            assert connected is True

            await channel_layer.group_send(
                f"dashboard.portfolio.{new_user.id}",
                {"type": "portfolio_composition_updated", "data": {"exposure": "10"}},
            )
            await client.wait()
            assert {"exposure": "10"} in client.sent_json_list()
            await client.disconnect()

        async_to_sync(scenario)()

    def test_positions_consumer_emits_bulk_snapshot_on_connect(self, new_user) -> None:
        async def scenario() -> None:
            client = _client(
                "positions", user=new_user, path="/ws/dashboard/positions/live/"
            )
            connected, _ = await client.connect()
            assert connected is True
            await client.wait()
            payloads = client.sent_json_list()
            assert any(p.get("type") == "position.snapshot_bulk" for p in payloads)
            await client.disconnect()

        async_to_sync(scenario)()

    def test_positions_consumer_receives_position_snapshot_update(
        self, new_user, channel_layer
    ) -> None:
        async def scenario() -> None:
            client = _client(
                "positions", user=new_user, path="/ws/dashboard/positions/live/"
            )
            connected, _ = await client.connect()
            assert connected is True

            await channel_layer.group_send(
                f"dashboard.positions.{new_user.id}",
                {"type": "position_snapshot_updated", "data": {"position_id": "p1"}},
            )
            await client.wait()
            payloads = client.sent_json_list()
            assert any(
                p.get("type") == "position.snapshot_updated"
                and p.get("data", {}).get("position_id") == "p1"
                for p in payloads
            )
            await client.disconnect()

        async_to_sync(scenario)()

    def test_orders_consumer_receives_status_change(self, new_user, channel_layer) -> None:
        async def scenario() -> None:
            client = _client("orders", user=new_user, path="/ws/dashboard/orders/")
            connected, _ = await client.connect()
            assert connected is True

            await channel_layer.group_send(
                f"dashboard.orders.{new_user.id}",
                {"type": "order_status_changed", "data": {"order_id": "abc"}},
            )
            await client.wait()
            payloads = client.sent_json_list()
            assert any(
                p.get("type") == "order.status_changed"
                and p.get("data", {}).get("order_id") == "abc"
                for p in payloads
            )
            await client.disconnect()

        async_to_sync(scenario)()


class TestIsolation:
    def test_users_receive_only_their_own_group(self, new_user, channel_layer) -> None:
        other = User.objects.create_user(
            username="ws-other-isolated", password="SecurePass123!"
        )

        async def scenario() -> None:
            client_a = _client("home", user=new_user, path="/ws/dashboard/home/")
            client_b = _client("home", user=other, path="/ws/dashboard/home/")
            connected_a, _ = await client_a.connect()
            connected_b, _ = await client_b.connect()
            assert connected_a and connected_b

            await channel_layer.group_send(
                f"dashboard.home.{new_user.id}",
                {"type": "home_summary_updated", "data": {"cash": "100"}},
            )
            await client_a.wait()
            await client_b.wait()

            assert {"cash": "100"} in client_a.sent_json_list()
            assert client_b.sent_json_list() == []
            await client_a.disconnect()
            await client_b.disconnect()

        async_to_sync(scenario)()


class TestDisconnect:
    def test_disconnect_removes_channel_from_group(
        self, new_user, channel_layer
    ) -> None:
        async def scenario() -> None:
            client = _client("home", user=new_user, path="/ws/dashboard/home/")
            connected, _ = await client.connect()
            assert connected is True
            group = f"dashboard.home.{new_user.id}"
            assert group in channel_layer.groups

            await client.disconnect()
            await client.wait()
            assert group not in channel_layer.groups

        async_to_sync(scenario)()


class TestClientFrames:
    def test_receive_json_is_noop_and_does_not_crash(self, new_user) -> None:
        async def scenario() -> None:
            client = _client("home", user=new_user, path="/ws/dashboard/home/")
            connected, _ = await client.connect()
            assert connected is True

            await client.receive('{"not": "an event"}')
            await client.wait()
            assert client.sent_json_list() == []
            await client.disconnect()

        async_to_sync(scenario)()
