"""NEWS-FEED-1 — intelligence ``NewsContext`` builder.

Builds the ``core.events.event_types.NewsContext`` for a symbol from ingested
news rows, for use by the intelligence packet bridges
(``trading_signal_bridge`` / ``ta_completed_handler``).

Semantics for "missing vs never checked" (ADR-029 §5):
- ``build()`` returns ``(NewsContext, checked)``. ``checked=True`` means a real
  repository query ran (even if it found nothing); ``checked=False`` means the
  lookup could not run (store unavailable) and the caller must keep the
  ``missing: ["news"]`` tag as "never checked".
- Sentiment in the packet is a coarse 4-bucket mapping of the *provider's*
  score (ADR-029 §2). A missing score maps to ``NEUTRAL`` (absence), never a
  fabricated value. Materiality is not assessed in this batch and is always
  ``LOW`` (the ``NewsItem`` dataclass baseline).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from apps.news_feed.application.ports import NewsItemRepository
from apps.news_feed.domain.entities import NewsItem as StoredNewsItem
from core.clock import get_clock
from core.events.event_types import (
    AggregateSentiment,
    MaterialityLevel,
    NewsContext,
    NewsItem,
)

_POSITIVE_THRESHOLD = 0.25
_NEGATIVE_THRESHOLD = -0.25


class NewsContextService:
    """Assemble a symbol's ``NewsContext`` over a rolling lookback window."""

    def __init__(
        self,
        repository: NewsItemRepository,
        *,
        lookback_minutes: int,
        max_headlines: int,
    ) -> None:
        self._repository = repository
        self._lookback_minutes = lookback_minutes
        self._max_headlines = max_headlines

    def build(
        self,
        symbol: str,
        *,
        as_of: datetime | None = None,
    ) -> tuple[NewsContext, bool]:
        """Return ``(news_context, checked)`` for ``symbol``."""
        as_of = as_of or get_clock().now()
        try:
            rows = self._repository.recent_for_symbol(
                symbol,
                limit=self._max_headlines,
                published_after=as_of - timedelta(minutes=self._lookback_minutes),
            )
        except Exception:
            # Store unavailable — caller treats this as "never checked".
            return NewsContext(), False

        if not rows:
            return NewsContext(), True

        headlines = tuple(_to_packet_item(row, as_of) for row in rows)
        aggregate = _aggregate_sentiment(
            [row.sentiment_score for row in rows]
        )
        return NewsContext(headlines=headlines, aggregate_sentiment=aggregate), True


def get_news_context_service() -> NewsContextService:
    """Return the default service wired to the ORM store + config window."""
    from apps.news_feed.infrastructure.repositories import NewsItemRepository
    from core.config import config

    return NewsContextService(
        repository=NewsItemRepository(),
        lookback_minutes=config.news_lookback_minutes,
        max_headlines=config.news_max_headlines,
    )


def _to_packet_item(row: StoredNewsItem, as_of: datetime) -> NewsItem:
    """Map a stored news row onto the packet ``NewsItem`` dataclass."""
    age_minutes = max(int((as_of - row.published_at).total_seconds() // 60), 0)
    return NewsItem(
        title=row.headline,
        source=row.source,
        sentiment=_sentiment_from_score(row.sentiment_score),
        materiality=MaterialityLevel.LOW,
        age_minutes=age_minutes,
        url=row.url,
    )


def _sentiment_from_score(score) -> AggregateSentiment:
    """Coarse bucket of the provider-supplied score; None → NEUTRAL (absence)."""
    if score is None:
        return AggregateSentiment.NEUTRAL
    value = float(score)
    if value >= _POSITIVE_THRESHOLD:
        return AggregateSentiment.POSITIVE
    if value <= _NEGATIVE_THRESHOLD:
        return AggregateSentiment.NEGATIVE
    return AggregateSentiment.NEUTRAL


def _aggregate_sentiment(scores: list) -> AggregateSentiment:
    """Aggregate provider scores into the packet's ``AggregateSentiment``.

    MIXED when both sides of the threshold appear; otherwise the mean score
    bucketed by the same thresholds; NEUTRAL when no score is present.
    """
    present = [float(s) for s in scores if s is not None]
    if not present:
        return AggregateSentiment.NEUTRAL
    if any(s >= _POSITIVE_THRESHOLD for s in present) and any(
        s <= _NEGATIVE_THRESHOLD for s in present
    ):
        return AggregateSentiment.MIXED
    mean = sum(present) / len(present)
    if mean >= _POSITIVE_THRESHOLD:
        return AggregateSentiment.POSITIVE
    if mean <= _NEGATIVE_THRESHOLD:
        return AggregateSentiment.NEGATIVE
    return AggregateSentiment.NEUTRAL
