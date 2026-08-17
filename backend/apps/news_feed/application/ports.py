"""NEWS-FEED-1 — application ports (interfaces).

The application services depend only on these protocols, never on Django ORM
models or a concrete provider class — mirroring ``apps/execution/application/
ports.py`` (``BrokerAdapter``). This keeps ingestion, budget enforcement, and
the intelligence ``NewsContext`` lookup testable with in-memory fakes and the
provider swappable via ``NEWS_PROVIDER``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Protocol, runtime_checkable

from apps.news_feed.domain.entities import NewsItem


@runtime_checkable
class NewsProvider(Protocol):
    """Fetch the latest headlines from a licensed news API."""

    provider_name: str

    def fetch_latest(
        self,
        *,
        symbols: list[str],
        limit: int,
        published_after: datetime | None = None,
    ) -> list[NewsItem]:
        """Return the most recent articles for ``symbols``.

        Raises ``NewsProviderError`` on transport/parse failure and
        ``NewsProviderRateLimited`` when the provider signals a rate limit.
        """
        ...

    def health_check(self) -> dict[str, Any]:
        """Return a provider health report (status, note)."""
        ...


@runtime_checkable
class NewsItemRepository(Protocol):
    """Persistence interface for ingested news items."""

    def upsert_many(self, items: Iterable[NewsItem]) -> int:
        """Insert new rows idempotently; return the number actually inserted.

        Dedup is on ``(source, url)`` via the model's unique constraint —
        a re-poll of the same article is a no-op, never a duplicate row.
        """
        ...

    def recent_for_symbol(
        self,
        symbol: str,
        *,
        limit: int,
        published_after: datetime | None = None,
    ) -> list[NewsItem]:
        """Return the most recent items tagged with ``symbol``."""
        ...

    def count(self) -> int:
        """Total rows in the store (for observability)."""
        ...


@runtime_checkable
class DailyCallBudget(Protocol):
    """Enforces a per-day provider call budget read from settings."""

    def try_reserve(self, calls: int = 1) -> bool:
        """Reserve ``calls`` against today's budget; False when exhausted."""
        ...

    def used_today(self) -> int:
        """Number of provider calls consumed today."""
        ...
