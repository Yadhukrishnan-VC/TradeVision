"""news_feed.views — flat-shim re-exports (canonical: interfaces/api/views)."""

from __future__ import annotations

from apps.news_feed.interfaces.api.views import (
    NewsItemDetailView,
    NewsItemListView,
)

__all__ = ["NewsItemListView", "NewsItemDetailView"]
