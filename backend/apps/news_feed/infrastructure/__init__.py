"""news_feed.infrastructure."""

from __future__ import annotations

from apps.news_feed.infrastructure.models import NewsItem
from apps.news_feed.infrastructure.repositories import NewsItemRepository

__all__ = ["NewsItem", "NewsItemRepository"]
