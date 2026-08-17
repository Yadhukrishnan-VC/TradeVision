"""NEWS-FEED-1 — news ingestion service.

Orchestrates provider fetch → dedup persistence → per-item domain events.
Re-runs are idempotent: the ``(source, url)`` unique constraint makes a
repeated fetch of the same article a no-op.

Rate-limit discipline (ADR-029 §4):
- The daily provider budget is enforced BEFORE any fetch via ``DailyCallBudget``
  (read from ``NEWS_RATE_LIMIT_CALLS_PER_DAY``); exhausting it is logged as a
  skip, never an error.
- A provider-signalled rate limit (429/402) raises ``NewsProviderRateLimited``
  so the Celery task can retry with exponential backoff.
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta

from apps.news_feed.application.ports import (
    DailyCallBudget,
    NewsItemRepository,
    NewsProvider,
)
from apps.news_feed.domain.exceptions import NewsProviderError
from core.clock import get_clock
from core.metrics import (
    NEWS_INGESTED_TOTAL,
    NEWS_INGESTION_ERRORS_TOTAL,
    NEWS_PROVIDER_LATENCY_SECONDS,
    NEWS_RATE_LIMIT_EXHAUSTED_TOTAL,
)

logger = logging.getLogger(__name__)


class NewsIngestionService:
    """Fetch the latest headlines for the configured symbols and store them."""

    def __init__(
        self,
        provider: NewsProvider,
        repository: NewsItemRepository,
        budget: DailyCallBudget,
        *,
        poll_symbols: list[str],
        articles_per_request: int,
        lookback_minutes: int,
        publisher: object | None = None,
    ) -> None:
        self._provider = provider
        self._repository = repository
        self._budget = budget
        self._poll_symbols = list(poll_symbols)
        self._articles_per_request = articles_per_request
        self._lookback_minutes = lookback_minutes
        self._publisher = publisher

    def run(self, *, correlation_id: str = "") -> dict:
        """Fetch + store the latest news. Returns a run summary dict.

        Raises ``NewsProviderError`` (incl. ``NewsProviderRateLimited``) so the
        caller can retry; budget-exhaustion and no-symbol cases return a
        summary with ``skipped`` set and never raise.
        """
        if not self._poll_symbols:
            logger.info("news_ingestion_no_symbols")
            return {"fetched": 0, "inserted": 0, "skipped": "no_symbols", "errors": []}

        if not self._budget.try_reserve(1):
            NEWS_RATE_LIMIT_EXHAUSTED_TOTAL.inc()
            logger.warning(
                "news_ingestion_rate_limit_exhausted",
                extra={"provider": self._provider.provider_name},
            )
            return {"fetched": 0, "inserted": 0, "skipped": "rate_limit", "errors": []}

        published_after = get_clock().now() - timedelta(minutes=self._lookback_minutes)

        started = time.monotonic()
        try:
            items = self._provider.fetch_latest(
                symbols=self._poll_symbols,
                limit=self._articles_per_request,
                published_after=published_after,
            )
        except NewsProviderError:
            NEWS_INGESTION_ERRORS_TOTAL.labels(error_type="provider").inc()
            raise
        latency = round(time.monotonic() - started, 4)
        NEWS_PROVIDER_LATENCY_SECONDS.observe(latency)

        inserted = self._repository.upsert_many(items)
        for item in inserted:
            NEWS_INGESTED_TOTAL.labels(
                symbol=_primary_symbol(item.symbols),
                source=item.source,
            ).inc()
            if self._publisher is not None:
                try:
                    self._publisher.publish_ingested(item, correlation_id=correlation_id)
                except Exception as exc:  # never let event publishing fail ingestion
                    logger.warning(
                        "news_ingested_event_publish_failed",
                        extra={"url": item.url, "error": str(exc)},
                    )

        logger.info(
            "news_ingestion_run_complete",
            extra={
                "provider": self._provider.provider_name,
                "fetched": len(items),
                "inserted": len(inserted),
                "duplicates": len(items) - len(inserted),
                "latency_ms": round(latency * 1000, 2),
            },
        )
        return {
            "fetched": len(items),
            "inserted": len(inserted),
            "skipped": None,
            "errors": [],
        }


def _primary_symbol(symbols: frozenset[str]) -> str:
    """Pick a stable single symbol label for metrics."""
    return sorted(symbols)[0] if symbols else "UNKNOWN"


def get_ingestion_service() -> NewsIngestionService:
    """Return the default service wired to the configured provider + ORM store."""
    from apps.news_feed.infrastructure.event_publishers import NewsEventPublisher
    from apps.news_feed.infrastructure.providers.fake_provider import FakeNewsProvider
    from apps.news_feed.infrastructure.providers.marketaux_provider import (
        MarketauxNewsProvider,
    )
    from apps.news_feed.infrastructure.rate_budget import CacheDailyCallBudget
    from apps.news_feed.infrastructure.repositories import NewsItemRepository
    from core.config import config

    provider: NewsProvider
    if config.news_provider == "marketaux":
        provider = MarketauxNewsProvider()
    elif config.news_provider == "fake":
        provider = FakeNewsProvider()
    else:
        raise ValueError(f"Unsupported NEWS_PROVIDER: {config.news_provider!r}")

    return NewsIngestionService(
        provider=provider,
        repository=NewsItemRepository(),
        budget=CacheDailyCallBudget(daily_cap=config.news_rate_limit_calls_per_day),
        poll_symbols=config.news_poll_symbols,
        articles_per_request=config.news_articles_per_request,
        lookback_minutes=config.news_lookback_minutes,
        publisher=NewsEventPublisher(),
    )
