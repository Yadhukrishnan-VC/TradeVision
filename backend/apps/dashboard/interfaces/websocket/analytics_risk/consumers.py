from __future__ import annotations

import json
from typing import Any

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from apps.dashboard.infrastructure.analytics_risk.cache import PnLWebSocketDebounceCache, RiskDebounceCache


class PnLConsumer(AsyncJsonWebsocketConsumer):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._account_id: str | None = None
        self._debounce = PnLWebSocketDebounceCache()

    async def connect(self) -> None:
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4029)
            return

        account_id = self.scope["url_route"]["kwargs"]["account_id"]
        if str(account_id) != str(user.id):
            await self.close(code=4029)
            return

        self._account_id = str(account_id)

        await self.channel_layer.group_add(
            f"pnl_{self._account_id}",
            self.channel_name,
        )
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        if self._account_id:
            await self.channel_layer.group_discard(
                f"pnl_{self._account_id}",
                self.channel_name,
            )

    async def receive_json(self, content: dict[str, Any]) -> None:
        await self.send_json({"status": "ok", "message": "PnL consumer connected"})

    async def pnl_update(self, event: dict[str, Any]) -> None:
        data = event.get("data", {})
        await self.send_json(data)


class RiskConsumer(AsyncJsonWebsocketConsumer):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._account_id: str | None = None
        self._debounce = RiskDebounceCache()

    async def connect(self) -> None:
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4029)
            return

        account_id = self.scope["url_route"]["kwargs"]["account_id"]
        if str(account_id) != str(user.id):
            await self.close(code=4029)
            return

        self._account_id = str(account_id)

        await self.channel_layer.group_add(
            f"risk_{self._account_id}",
            self.channel_name,
        )
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        if self._account_id:
            await self.channel_layer.group_discard(
                f"risk_{self._account_id}",
                self.channel_name,
            )

    async def receive_json(self, content: dict[str, Any]) -> None:
        await self.send_json({"status": "ok", "message": "Risk consumer connected"})

    async def risk_update(self, event: dict[str, Any]) -> None:
        data = event.get("data", {})
        await self.send_json(data)
