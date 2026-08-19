"""WS3 — analytics-risk WebSocket consumer production tests.

The PnL / Risk consumers historically accepted any ``account_id`` in the URL
with no authentication or ownership check (cross-user data exposure). These
tests lock in the fix: unauthenticated and cross-account connections are
rejected with close code 4029, and only the account owner receives updates.
"""

from __future__ import annotations

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model

from apps.dashboard.tests.websocket.conftest import (
    ANALYTICS_APPS,
    WSClient,
    build_scope,
)

User = get_user_model()


def _client(name: str, *, user, account_id: str) -> WSClient:
    path = f"/ws/dashboard/accounts/{account_id}/pnl/" if name == "pnl" else f"/ws/dashboard/accounts/{account_id}/risk/"
    return WSClient(
        ANALYTICS_APPS[name],
        build_scope(user=user, path=path, account_id=account_id),
    )


class TestAuthentication:
    def test_consumers_reject_missing_user(self) -> None:
        async def scenario() -> None:
            for name in ANALYTICS_APPS:
                client = _client(name, user=None, account_id="00000000-0000-0000-0000-000000000001")
                connected, close = await client.connect()
                assert connected is False
                assert close is not None and close.get("code") == 4029
                await client.disconnect()

        async_to_sync(scenario)()

    def test_consumers_reject_anonymous_user(self, anonymous_user) -> None:
        async def scenario() -> None:
            for name in ANALYTICS_APPS:
                client = _client(name, user=anonymous_user, account_id="00000000-0000-0000-0000-000000000001")
                connected, close = await client.connect()
                assert connected is False
                assert close is not None and close.get("code") == 4029
                await client.disconnect()

        async_to_sync(scenario)()


class TestAccountOwnership:
    def test_consumer_rejects_foreign_account_id(self, new_user, channel_layer) -> None:
        other = User.objects.create_user(
            username="ws-other-owner", password="SecurePass123!"
        )

        async def scenario() -> None:
            for name in ANALYTICS_APPS:
                client = _client(name, user=new_user, account_id=str(other.id))
                connected, close = await client.connect()
                assert connected is False
                assert close is not None and close.get("code") == 4029
                await client.disconnect()

        async_to_sync(scenario)()

    def test_consumer_allows_own_account_id(self, new_user) -> None:
        async def scenario() -> None:
            for name in ANALYTICS_APPS:
                client = _client(name, user=new_user, account_id=str(new_user.id))
                connected, _ = await client.connect()
                assert connected is True
                await client.disconnect()

        async_to_sync(scenario)()


class TestDelivery:
    def test_pnl_consumer_receives_pnl_update(self, new_user, channel_layer) -> None:
        async def scenario() -> None:
            client = _client("pnl", user=new_user, account_id=str(new_user.id))
            connected, _ = await client.connect()
            assert connected is True

            await channel_layer.group_send(
                f"pnl_{new_user.id}",
                {"type": "pnl_update", "data": {"current_total_pnl": "42"}},
            )
            await client.wait()
            assert {"current_total_pnl": "42"} in client.sent_json_list()
            await client.disconnect()

        async_to_sync(scenario)()

    def test_risk_consumer_receives_risk_update(self, new_user, channel_layer) -> None:
        async def scenario() -> None:
            client = _client("risk", user=new_user, account_id=str(new_user.id))
            connected, _ = await client.connect()
            assert connected is True

            await channel_layer.group_send(
                f"risk_{new_user.id}",
                {"type": "risk_update", "data": {"active_alerts": 3}},
            )
            await client.wait()
            assert {"active_alerts": 3} in client.sent_json_list()
            await client.disconnect()

        async_to_sync(scenario)()

    def test_receive_json_returns_status_ok(self, new_user) -> None:
        async def scenario() -> None:
            client = _client("pnl", user=new_user, account_id=str(new_user.id))
            connected, _ = await client.connect()
            assert connected is True

            await client.receive('{"hello": "world"}')
            await client.wait()
            payloads = client.sent_json_list()
            assert any(
                p.get("status") == "ok" and "connected" in p.get("message", "")
                for p in payloads
            )
            await client.disconnect()

        async_to_sync(scenario)()


class TestDisconnect:
    def test_disconnect_removes_channel_from_group(self, new_user, channel_layer) -> None:
        async def scenario() -> None:
            client = _client("pnl", user=new_user, account_id=str(new_user.id))
            connected, _ = await client.connect()
            assert connected is True
            group = f"pnl_{new_user.id}"
            assert group in channel_layer.groups

            await client.disconnect()
            await client.wait()
            assert group not in channel_layer.groups

        async_to_sync(scenario)()
