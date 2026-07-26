from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.conf import settings
from redis import Redis

from core.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj: object) -> object:
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, UUID):
            return str(obj)
        return super().default(obj)


class LatestPriceCache:
    KEY_PATTERN = "dashboard:price:latest:{symbol}"

    def __init__(self, redis_client: Redis | None = None) -> None:
        self._client = redis_client or get_redis_client()

    def set_price(self, symbol: str, price: Decimal) -> None:
        key = self.KEY_PATTERN.format(symbol=symbol)
        self._client.hset(key, mapping={"price": str(price)})

    def get_price(self, symbol: str) -> Decimal | None:
        key = self.KEY_PATTERN.format(symbol=symbol)
        data = self._client.hgetall(key)
        if not data:
            return None
        price_str = data.get("price", data.get(b"price", None))
        if price_str is None:
            return None
        if isinstance(price_str, bytes):
            price_str = price_str.decode("utf-8")
        return Decimal(price_str)

    def delete_price(self, symbol: str) -> None:
        key = self.KEY_PATTERN.format(symbol=symbol)
        self._client.delete(key)


class DashboardHomeCache:
    KEY_PATTERN = "dashboard:home:{account_id}"
    TTL_SECONDS = 30

    def __init__(self, redis_client: Redis | None = None) -> None:
        self._client = redis_client or get_redis_client()

    def set_summary(self, account_id: UUID, data: dict[str, Any]) -> None:
        key = self.KEY_PATTERN.format(account_id=account_id)
        serialized = json.dumps(data, cls=DecimalEncoder)
        self._client.setex(key, self.TTL_SECONDS, serialized)

    def get_summary(self, account_id: UUID) -> dict[str, Any] | None:
        key = self.KEY_PATTERN.format(account_id=account_id)
        data = self._client.get(key)
        if data is None:
            return None
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return json.loads(data)

    def delete_summary(self, account_id: UUID) -> None:
        key = self.KEY_PATTERN.format(account_id=account_id)
        self._client.delete(key)


class PortfolioDebounceCache:
    KEY_PATTERN = "dashboard:portfolio:debounce:{account_id}"
    TTL_SECONDS = 1

    def __init__(self, redis_client: Redis | None = None) -> None:
        self._client = redis_client or get_redis_client()

    def is_debounced(self, account_id: UUID) -> bool:
        key = self.KEY_PATTERN.format(account_id=account_id)
        return self._client.exists(key) > 0

    def mark(self, account_id: UUID) -> None:
        key = self.KEY_PATTERN.format(account_id=account_id)
        self._client.setex(key, self.TTL_SECONDS, "1")


class PositionDebounceCache:
    KEY_PATTERN = "dashboard:positions:debounce:{account_id}:{position_id}"
    TTL_SECONDS = 1

    def __init__(self, redis_client: Redis | None = None) -> None:
        self._client = redis_client or get_redis_client()

    def is_debounced(self, account_id: UUID, position_id: UUID) -> bool:
        key = self.KEY_PATTERN.format(account_id=account_id, position_id=position_id)
        return self._client.exists(key) > 0

    def mark(self, account_id: UUID, position_id: UUID) -> None:
        key = self.KEY_PATTERN.format(account_id=account_id, position_id=position_id)
        self._client.setex(key, self.TTL_SECONDS, "1")
