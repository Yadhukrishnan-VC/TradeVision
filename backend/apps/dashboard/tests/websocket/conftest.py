"""WS3 — WebSocket test harness.

``channels.testing.WebsocketCommunicator`` pulls in ``daphne``, which is not a
project dependency, so these tests drive consumer ASGI applications with a
minimal in-process harness that speaks the ASGI ``websocket`` protocol surface
the way a real server (Daphne) would:

- ``websocket.connect`` -> consumer ``connect()``
- ``websocket.receive`` (``text``) -> consumer ``receive_json()``
- ``websocket.disconnect`` -> consumer ``disconnect()``

Channel-layer events are delivered by the real ``InMemoryChannelLayer``
(configured in ``config.settings.testing``) via ``group_send``, so the tests
exercise the same code path a production consumer uses.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pytest
from channels.layers import get_channel_layer

from apps.dashboard.interfaces.websocket.analytics_risk.consumers import (
    PnLConsumer,
    RiskConsumer,
)
from apps.dashboard.interfaces.websocket.trading_core.consumers import (
    DashboardHomeConsumer,
    DashboardOrdersConsumer,
    DashboardPortfolioConsumer,
    DashboardPositionsConsumer,
)


class WSClient:
    """Drive a single consumer ASGI application through the websocket protocol."""

    def __init__(self, app: Any, scope: dict[str, Any]) -> None:
        self.app = app
        self.scope = scope
        self._incoming: list[dict[str, Any]] = []
        self._sent: list[dict[str, Any]] = []
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def _receive(self) -> dict[str, Any]:
        while not self._incoming:
            await self._wake.wait()
            self._wake.clear()
        return self._incoming.pop(0)

    async def _send(self, message: dict[str, Any]) -> None:
        self._sent.append(message)

    def _feed(self, message: dict[str, Any]) -> None:
        self._incoming.append(message)
        self._wake.set()

    async def start(self) -> None:
        self._task = asyncio.ensure_future(self.app(self.scope, self._receive, self._send))

    async def _wait_for_send(self, timeout: float = 1.0) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while not self._sent:
            if loop.time() >= deadline:
                return
            await asyncio.sleep(0.01)

    async def connect(self) -> tuple[bool, dict[str, Any] | None]:
        await self.start()
        self._feed({"type": "websocket.connect"})
        await self._wait_for_send()
        accept = self.sent_pop("websocket.accept")
        if accept is not None:
            return True, accept
        close = self.sent_pop("websocket.close")
        return False, close

    def sent_pop(self, msg_type: str) -> dict[str, Any] | None:
        for i, msg in enumerate(self._sent):
            if msg["type"] == msg_type:
                return self._sent.pop(i)
        return None

    def sent_json_list(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for msg in self._sent:
            if msg["type"] == "websocket.send":
                out.append(json.loads(msg["text"]))
        return out

    async def receive(self, text: str) -> None:
        self._feed({"type": "websocket.receive", "text": text})
        await self._wait_for_send()

    async def wait(self, timeout: float = 0.05) -> None:
        await asyncio.sleep(timeout)

    async def disconnect(self, code: int = 1000) -> None:
        self._feed({"type": "websocket.disconnect", "code": code})
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass


def build_scope(
    *,
    user: Any = None,
    path: str,
    account_id: str | None = None,
) -> dict[str, Any]:
    scope: dict[str, Any] = {
        "type": "websocket",
        "path": path,
        "query_string": b"",
        "headers": [],
        "subprotocols": [],
        "url_route": {"args": (), "kwargs": {}},
        "user": user,
    }
    if account_id is not None:
        scope["url_route"]["kwargs"]["account_id"] = account_id
    return scope


TRADING_CORE_APPS = {
    "home": DashboardHomeConsumer.as_asgi(),
    "portfolio": DashboardPortfolioConsumer.as_asgi(),
    "positions": DashboardPositionsConsumer.as_asgi(),
    "orders": DashboardOrdersConsumer.as_asgi(),
}

ANALYTICS_APPS = {
    "pnl": PnLConsumer.as_asgi(),
    "risk": RiskConsumer.as_asgi(),
}


@pytest.fixture
def channel_layer() -> Any:
    return get_channel_layer()


@pytest.fixture
def new_user(db: object) -> object:
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        username=f"ws-{uuid.uuid4().hex[:8]}",
        password="SecurePass123!",
    )


@pytest.fixture
def anonymous_user() -> Any:
    from django.contrib.auth.models import AnonymousUser

    return AnonymousUser()
