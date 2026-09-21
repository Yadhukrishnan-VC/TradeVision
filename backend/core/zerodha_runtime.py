"""Runtime (Redis-backed) Zerodha access-token override.

The auth callback exchanges a request_token for an access_token and persists
it to the active .env file for the next stack start. That file change only
takes effect on a container recreate, so the exchanged token is ALSO stored
here (Redis, TTL until the next day's login-window reset) and read by
``core.config.config.zerodha_access_token`` before falling back to
``settings.ZERODHA_ACCESS_TOKEN``.

This module deliberately imports no broker code to keep ``core.config``
import-cycle free.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

REDIS_TOKEN_KEY = "zerodha:shed:hot:access_token"
# Access tokens are invalidated at the next day's login-window reset; a TTL
# keeps the override self-cleaning even if a restart never happens.
DEFAULT_TTL_SECONDS = 24 * 60 * 60


def get_hot_access_token() -> str | None:
    try:
        from core.redis_client import get_redis_client

        client = get_redis_client()
        token = client.get(REDIS_TOKEN_KEY)
        return token if token else None
    except Exception:  # noqa: BLE001 - never let Redis break the hot path
        return None


def set_hot_access_token(token: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> bool:
    try:
        from core.redis_client import get_redis_client

        client = get_redis_client()
        client.set(REDIS_TOKEN_KEY, token, ex=ttl_seconds)
        return True
    except Exception:  # noqa: BLE001
        logger.warning("zerodha_hot_token_set_failed")
        return False


def clear_hot_access_token() -> None:
    try:
        from core.redis_client import get_redis_client

        get_redis_client().delete(REDIS_TOKEN_KEY)
    except Exception:  # noqa: BLE001
        logger.warning("zerodha_hot_token_clear_failed")


def hot_token_ttl() -> int | None:
    """Seconds until the hot override expires (None if not set / Redis error)."""
    try:
        from core.redis_client import get_redis_client

        ttl = int(get_redis_client().ttl(REDIS_TOKEN_KEY))
        return ttl if ttl >= 0 else None
    except Exception:  # noqa: BLE001
        return None