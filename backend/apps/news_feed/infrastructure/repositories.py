"""NEWS-FEED-1 — Django ORM repository.

Implements ``NewsItemRepository`` (the application-layer protocol) against the
``NewsItem`` table. Dedup is enforced by the ``(source, url)`` unique
constraint: ``upsert_many`` filters out keys already present so the inserted
set is exact and re-polls are no-ops.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Iterable

from django.db.models import Q

from apps.news_feed.application.ports import NewsItemRepository
from apps.news_feed.domain.entities import NewsItem
from apps.news_feed.infrastructure.models import NewsItem as NewsItemModel


class NewsItemRepository(NewsItemRepository):  # type: ignore[misc]
    """Persistence for the ingested news store."""

    def upsert_many(self, items: Iterable[NewsItem]) -> list[NewsItem]:
        """Insert rows whose ``(source, url)`` is not already stored.

        Returns the newly inserted domain entities (empty list when everything
        was already present — a re-poll of unchanged articles is a no-op).
        """
        items = list(items)
        if not items:
            return []

        existing = self._existing_keys(items)
        fresh = [item for item in items if (item.source, item.url) not in existing]
        if not fresh:
            return []

        rows = [
            NewsItemModel(
                provider_id=item.provider_id,
                source=item.source,
                headline=item.headline,
                body=item.body or "",
                url=item.url,
                published_at=item.published_at,
                symbols=sorted(item.symbols),
                sentiment_score=item.sentiment_score,
                sentiment_label=item.sentiment_label,
            )
            for item in fresh
        ]
        NewsItemModel.objects.bulk_create(rows)
        return [
            NewsItem(
                id=row.id,
                source=row.source,
                headline=row.headline,
                body=row.body or None,
                url=row.url,
                published_at=row.published_at,
                provider_id=row.provider_id,
                symbols=frozenset(row.symbols or []),
                sentiment_score=row.sentiment_score,
                sentiment_label=row.sentiment_label,
                ingested_at=row.ingested_at,
            )
            for row in rows
        ]

    def recent_for_symbol(
        self,
        symbol: str,
        *,
        limit: int,
        published_after: datetime | None = None,
    ) -> list[NewsItem]:
        queryset = NewsItemModel.objects.filter(symbols__contains=[symbol])
        if published_after is not None:
            queryset = queryset.filter(published_at__gte=published_after)
        rows = queryset.order_by("-published_at")[:limit]
        return [_to_domain(row) for row in rows]

    def count(self) -> int:
        return NewsItemModel.objects.count()

    @staticmethod
    def _existing_keys(items: list[NewsItem]) -> set[tuple[str, str]]:
        if not items:
            return set()
        query = Q()
        for item in items:
            query |= Q(source=item.source, url=item.url)
        return set(
            NewsItemModel.objects.filter(query).values_list("source", "url")
        )


def _to_domain(row: NewsItemModel) -> NewsItem:
    return NewsItem(
        id=row.id,
        source=row.source,
        headline=row.headline,
        body=row.body or None,
        url=row.url,
        published_at=row.published_at,
        provider_id=row.provider_id,
        symbols=frozenset(row.symbols or []),
        sentiment_score=_as_decimal(row.sentiment_score),
        sentiment_label=row.sentiment_label,
        ingested_at=row.ingested_at,
    )


def _as_decimal(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))
