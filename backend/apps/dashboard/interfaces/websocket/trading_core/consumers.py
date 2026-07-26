from __future__ import annotations

import json
import logging
from typing import Any

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.dashboard.application.trading_core.services.live_positions_service import (
    LivePositionsService,
)

logger = logging.getLogger(__name__)


class DashboardHomeConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        self.user = self.scope.get("user")
        if self.user is None or not self.user.is_authenticated:
            await self.close(code=4029)
            return

        self.account_id = str(self.user.id)
        self.group_name = f"dashboard.home.{self.account_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        logger.info(
            "WebSocket connected",
            extra={"group": self.group_name, "user": str(self.user.id)},
        )

    async def disconnect(self, close_code: int) -> None:
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content: dict[str, Any], **kwargs: Any) -> None:
        pass

    async def home_summary_updated(self, event: dict[str, Any]) -> None:
        await self.send_json(event["data"])


class DashboardPortfolioConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        self.user = self.scope.get("user")
        if self.user is None or not self.user.is_authenticated:
            await self.close(code=4029)
            return

        self.account_id = str(self.user.id)
        self.group_name = f"dashboard.portfolio.{self.account_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        logger.info(
            "Portfolio WebSocket connected",
            extra={"group": self.group_name, "user": str(self.user.id)},
        )

    async def disconnect(self, close_code: int) -> None:
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content: dict[str, Any], **kwargs: Any) -> None:
        pass

    async def portfolio_composition_updated(self, event: dict[str, Any]) -> None:
        await self.send_json(event["data"])


class DashboardPositionsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        self.user = self.scope.get("user")
        if self.user is None or not self.user.is_authenticated:
            await self.close(code=4029)
            return

        self.account_id = str(self.user.id)
        self.group_name = f"dashboard.positions.{self.account_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        positions = self._get_bulk_snapshot()
        await self.send_json({
            "type": "position.snapshot_bulk",
            "data": positions,
        })

        logger.info(
            "Positions WebSocket connected",
            extra={"group": self.group_name, "user": str(self.user.id)},
        )

    def _get_bulk_snapshot(self) -> list[dict[str, Any]]:
        try:
            service = LivePositionsService()
            dtos = service.list_open(self.user.id)
            return [
                {
                    "position_id": str(d.position_id),
                    "symbol": d.symbol,
                    "side": d.side,
                    "quantity": str(d.quantity),
                    "entry_price": str(d.entry_price),
                    "current_price": str(d.current_price) if d.current_price else None,
                    "unrealized_pnl": str(d.unrealized_pnl) if d.unrealized_pnl else None,
                    "is_open": d.is_open,
                    "opened_at": d.opened_at.isoformat() if d.opened_at else None,
                }
                for d in dtos
            ]
        except Exception:
            logger.exception("Failed to get bulk snapshot for WebSocket")
            return []

    async def disconnect(self, close_code: int) -> None:
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content: dict[str, Any], **kwargs: Any) -> None:
        pass

    async def position_snapshot_updated(self, event: dict[str, Any]) -> None:
        await self.send_json({
            "type": "position.snapshot_updated",
            "data": event["data"],
        })


class DashboardOrdersConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        self.user = self.scope.get("user")
        if self.user is None or not self.user.is_authenticated:
            await self.close(code=4029)
            return

        self.account_id = str(self.user.id)
        self.group_name = f"dashboard.orders.{self.account_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        logger.info(
            "Orders WebSocket connected",
            extra={"group": self.group_name, "user": str(self.user.id)},
        )

    async def disconnect(self, close_code: int) -> None:
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content: dict[str, Any], **kwargs: Any) -> None:
        pass

    async def order_status_changed(self, event: dict[str, Any]) -> None:
        await self.send_json({
            "type": "order.status_changed",
            "data": event["data"],
        })
