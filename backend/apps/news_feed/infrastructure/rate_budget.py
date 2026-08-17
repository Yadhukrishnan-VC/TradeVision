"""NEWS-FEED-1 — per-day provider call budget.

Enforces ``NEWS_RATE_LIMIT_CALLS_PER_DAY`` (read from settings, never
hardcoded) against a daily counter. The cache backend is Redis in production
(atomic ``incr``); tests can inject ``InMemoryDailyCallBudget`` directly or
point the cache at LocMem.
"""

from __future__ import annotations

from datetime import date

from django.core.cache import cache

from apps.news_feed.application.ports import DailyCallBudget


class CacheDailyCallBudget:
    """Daily call budget backed by the Django cache (atomic incr)."""

    def __init__(
        self,
        *,
        daily_cap: int,
        key_prefix: str = "news:rate_budget",
        ttl_seconds: int = 60 * 60 * 24 + 60,
    ) -> None:
        self._daily_cap = max(daily_cap, 0)
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds

    def try_reserve(self, calls: int = 1) -> bool:
        """Atomically reserve ``calls`` against today's budget.

        Returns False when the reservation would exceed the daily cap (the
        caller skips the fetch, logged, not an error). A rejected reservation
        is undone so rejected attempts never consume budget.
        """
        if self._daily_cap <= 0:
            return False
        key = self._daily_key()
        used = self._incr(key, calls)
        if used <= self._daily_cap:
            return True
        # Rejected reservation — undo the increment. Best-effort (not atomic);
        # the cap re-check on the next attempt bounds any drift.
        try:
            cache.decr(key, calls)
        except ValueError:
            pass
        return False

    def used_today(self) -> int:
        return int(cache.get(self._daily_key(), 0))

    def _daily_key(self) -> str:
        return f"{self._key_prefix}:{date.today().isoformat()}"

    def _incr(self, key: str, calls: int) -> int:
        try:
            return cache.incr(key, calls)
        except ValueError:
            # Key missing (or dummy cache without incr). Try to seed it first.
            if cache.add(key, calls, timeout=self._ttl_seconds):
                return calls
            return cache.incr(key, calls)


class InMemoryDailyCallBudget:
    """In-memory daily budget for tests — same semantics, no cache."""

    def __init__(self, *, daily_cap: int) -> None:
        self._daily_cap = daily_cap
        self._used = 0

    def try_reserve(self, calls: int = 1) -> bool:
        if self._used + calls > self._daily_cap:
            return False
        self._used += calls
        return True

    def used_today(self) -> int:
        return self._used
