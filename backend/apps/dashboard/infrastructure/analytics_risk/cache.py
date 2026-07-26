from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from uuid import UUID

from redis import Redis

from core.redis_client import get_redis_client
from apps.dashboard.infrastructure.trading_core.cache import DecimalEncoder


class RiskLatestCache:
    KEY_PATTERN = "dashboard:risk:latest:{account_id}"
    TTL_SECONDS = 30

    def __init__(self, redis_client: Redis | None = None) -> None:
        self._client = redis_client or get_redis_client()

    def set_snapshot(self, account_id: UUID, data: dict[str, Any]) -> None:
        key = self.KEY_PATTERN.format(account_id=account_id)
        serialized = json.dumps(data, cls=DecimalEncoder)
        self._client.setex(key, self.TTL_SECONDS, serialized)

    def get_snapshot(self, account_id: UUID) -> dict[str, Any] | None:
        key = self.KEY_PATTERN.format(account_id=account_id)
        data = self._client.get(key)
        if data is None:
            return None
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return json.loads(data)

    def delete_snapshot(self, account_id: UUID) -> None:
        key = self.KEY_PATTERN.format(account_id=account_id)
        self._client.delete(key)


class PerformanceCache:
    KEY_PATTERN = "dashboard:performance:{account_id}:{period}"
    TTL_SECONDS = 300

    def __init__(self, redis_client: Redis | None = None) -> None:
        self._client = redis_client or get_redis_client()

    def set_metrics(self, account_id: UUID, period: str, data: dict[str, Any]) -> None:
        key = self.KEY_PATTERN.format(account_id=account_id, period=period)
        serialized = json.dumps(data, cls=DecimalEncoder)
        self._client.setex(key, self.TTL_SECONDS, serialized)

    def get_metrics(self, account_id: UUID, period: str) -> dict[str, Any] | None:
        key = self.KEY_PATTERN.format(account_id=account_id, period=period)
        data = self._client.get(key)
        if data is None:
            return None
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return json.loads(data)

    def delete_metrics(self, account_id: UUID, period: str) -> None:
        key = self.KEY_PATTERN.format(account_id=account_id, period=period)
        self._client.delete(key)


class PnLWebSocketDebounceCache:
    KEY_PATTERN = "dashboard:pnl:debounce:{account_id}"
    TTL_SECONDS = 1

    def __init__(self, redis_client: Redis | None = None) -> None:
        self._client = redis_client or get_redis_client()

    def is_debounced(self, account_id: UUID) -> bool:
        key = self.KEY_PATTERN.format(account_id=account_id)
        return self._client.exists(key) > 0

    def mark(self, account_id: UUID) -> None:
        key = self.KEY_PATTERN.format(account_id=account_id)
        self._client.setex(key, self.TTL_SECONDS, "1")


class RiskDebounceCache:
    KEY_PATTERN = "dashboard:risk:debounce:{account_id}"
    TTL_SECONDS = 2

    def __init__(self, redis_client: Redis | None = None) -> None:
        self._client = redis_client or get_redis_client()

    def is_debounced(self, account_id: UUID) -> bool:
        key = self.KEY_PATTERN.format(account_id=account_id)
        return self._client.exists(key) > 0

    def mark(self, account_id: UUID) -> None:
        key = self.KEY_PATTERN.format(account_id=account_id)
        self._client.setex(key, self.TTL_SECONDS, "1")
