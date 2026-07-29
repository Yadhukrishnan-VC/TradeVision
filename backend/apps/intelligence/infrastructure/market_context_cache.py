from __future__ import annotations

import dataclasses
import json
import logging
from typing import Any

from django.conf import settings

from apps.intelligence.domain.market_regime import MarketRegime, MultiTimeframeAlignment
from core.events.event_bus import _EventEncoder
from core.events.event_types import PatternContext
from core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

CACHE_KEY_PREFIX = "market_context"


def _serialize(obj: Any) -> str:
    return json.dumps(dataclasses.asdict(obj), cls=_EventEncoder)


def _reconstruct_signal_context(data: dict[str, Any]) -> Any:
    from apps.intelligence.services import SignalContext

    if "market_regime" in data and isinstance(data["market_regime"], str):
        try:
            data["market_regime"] = MarketRegime(data["market_regime"])
        except ValueError:
            pass
    if "multi_timeframe_alignment" in data and isinstance(data["multi_timeframe_alignment"], str):
        try:
            data["multi_timeframe_alignment"] = MultiTimeframeAlignment(data["multi_timeframe_alignment"])
        except ValueError:
            pass
    if "trading_signal" in data and isinstance(data["trading_signal"], dict):
        from apps.intelligence.services import SignalContextRef
        try:
            data["trading_signal"] = SignalContextRef(**data["trading_signal"])
        except Exception:
            data["trading_signal"] = None
    return SignalContext(**data)


class MarketContextCache:
    def __init__(self, redis_client: Any | None = None) -> None:
        self._redis = redis_client

    def _client(self) -> Any:
        if self._redis is None:
            self._redis = get_redis_client()
        return self._redis

    def _key(self, symbol: str) -> str:
        return f"{CACHE_KEY_PREFIX}:{symbol}"

    def set(self, symbol: str, context: Any, ttl_seconds: int | None = None) -> None:
        try:
            client = self._client()
            ttl = ttl_seconds if ttl_seconds is not None else settings.MARKET_CONTEXT_CACHE_TTL_SECONDS
            client.setex(self._key(symbol), ttl, _serialize(context))
            logger.debug("market_context_cached", extra={"symbol": symbol, "ttl": ttl})
        except Exception as exc:
            logger.warning("market_context_cache_set_failed", extra={"symbol": symbol, "error": str(exc)})

    def get(self, symbol: str) -> Any | None:
        try:
            client = self._client()
            raw = client.get(self._key(symbol))
            if raw is None:
                return None
            data = json.loads(raw)
            return _reconstruct_signal_context(data)
        except Exception as exc:
            logger.warning("market_context_cache_get_failed", extra={"symbol": symbol, "error": str(exc)})
            return None

    def attach_pattern_context(self, symbol: str, pattern_context: PatternContext) -> None:
        try:
            client = self._client()
            raw = client.get(self._key(symbol))
            if raw is None:
                logger.debug("market_context_attach_skipped_no_entry", extra={"symbol": symbol})
                return
            data = json.loads(raw)
            data["pattern_alignment_note"] = pattern_context.top_analogue_summary or "PATTERN_ENGINE_NOT_AVAILABLE"
            existing_ttl = client.ttl(self._key(symbol))
            ttl = max(existing_ttl, 60) if existing_ttl > 0 else settings.MARKET_CONTEXT_CACHE_TTL_SECONDS
            client.setex(self._key(symbol), ttl, json.dumps(data))
            logger.info("market_context_pattern_attached", extra={"symbol": symbol})
        except Exception as exc:
            logger.warning("market_context_attach_failed", extra={"symbol": symbol, "error": str(exc)})
