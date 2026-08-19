"""NEWS-FEED-1 — news feed domain exceptions."""

from __future__ import annotations


class NewsFeedError(Exception):
    """Base class for all news-feed errors."""


class NewsProviderError(NewsFeedError):
    """Raised when a news provider fails or returns an unexpected response."""


class NewsProviderRateLimited(NewsProviderError):
    """Raised when the provider signals a rate limit (429/402 or header).

    The ingestion task retries this with exponential backoff; it never
    crashes the beat schedule.
    """
