"""news_feed.services — flat-shim re-exports (canonical: application.*)."""

from __future__ import annotations

from apps.news_feed.application.ingestion_service import (
    NewsIngestionService,
    get_ingestion_service,
)
from apps.news_feed.application.news_context_service import (
    NewsContextService,
    get_news_context_service,
)

__all__ = [
    "NewsIngestionService",
    "get_ingestion_service",
    "NewsContextService",
    "get_news_context_service",
]
