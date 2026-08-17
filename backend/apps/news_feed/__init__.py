"""news_feed — flat-shim re-exports (canonical: domain/application/infrastructure)."""

from __future__ import annotations

from apps.news_feed.application.ingestion_service import (
    NewsIngestionService,
    get_ingestion_service,
)
from apps.news_feed.application.news_context_service import (
    NewsContextService,
    get_news_context_service,
)
from apps.news_feed.domain.entities import NewsItem
from apps.news_feed.domain.value_objects import NewsProvider

__all__ = [
    "NewsIngestionService",
    "get_ingestion_service",
    "NewsContextService",
    "get_news_context_service",
    "NewsItem",
    "NewsProvider",
]
