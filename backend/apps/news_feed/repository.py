"""news_feed.repository — flat-shim re-exports (canonical: infrastructure/repositories)."""

from __future__ import annotations

from apps.news_feed.infrastructure.repositories import NewsItemRepository

__all__ = ["NewsItemRepository"]
