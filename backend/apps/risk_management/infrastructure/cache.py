from __future__ import annotations

import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

_KILL_SWITCH_KEY_PREFIX = "risk_management:kill_switch"
_DEFAULT_TTL_SECONDS = 10


class KillSwitchCache:
    """Short-TTL cache for kill-switch state.

    Reads are fail-closed: any cache error returns ``None`` so the caller
    (KillSwitchService) falls back to the database and, on any error there
    too, treats the kill switch as active.
    """

    def __init__(self, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds

    def _key(self, scope: str, symbol: str | None) -> str:
        return f"{_KILL_SWITCH_KEY_PREFIX}:{scope}:{symbol or '*'}"

    def get(self, scope: str, symbol: str | None = None) -> bool | None:
        """Return cached active-state, or ``None`` on miss/error (fail-closed)."""
        try:
            value = cache.get(self._key(scope, symbol))
        except Exception:
            logger.exception(
                "kill_switch_cache_read_error",
                extra={"scope": scope, "symbol": symbol},
            )
            return None
        if value is None:
            return None
        return bool(value)

    def set(self, scope: str, symbol: str | None, active: bool) -> None:
        try:
            cache.set(self._key(scope, symbol), bool(active), timeout=self._ttl)
        except Exception:
            logger.exception(
                "kill_switch_cache_write_error",
                extra={"scope": scope, "symbol": symbol},
            )

    def invalidate(self, scope: str, symbol: str | None = None) -> None:
        try:
            cache.delete(self._key(scope, symbol))
        except Exception:
            logger.exception(
                "kill_switch_cache_delete_error",
                extra={"scope": scope, "symbol": symbol},
            )
