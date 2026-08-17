"""news_feed.tasks — flat-shim re-export (canonical: infrastructure.tasks)."""

from __future__ import annotations

from apps.news_feed.infrastructure.tasks import ingest_news

__all__ = ["ingest_news"]
