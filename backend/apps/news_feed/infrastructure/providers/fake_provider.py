"""NEWS-FEED-1 — deterministic fake news provider.

Mirrors ``MarketauxNewsProvider``'s contract with a small canned set of
headlines so tests (and local development without a NEWS_API_KEY) can exercise
ingestion deterministically. The dataset is a reduced, synthetic stand-in for
real market news — never used in production.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from apps.news_feed.domain.entities import NewsItem


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _item(source: str, headline: str, symbol: str, score: Decimal | None, url: str, age_minutes: int) -> NewsItem:
    return NewsItem(
        source=source,
        headline=headline,
        body=f"Synthetic {symbol} news for {headline}.",
        url=url,
        published_at=_utc_now() - timedelta(minutes=age_minutes),
        provider_id=f"fake-{len(url)}",
        symbols=frozenset({symbol}),
        sentiment_score=score,
        sentiment_label=None,
    )


_CANNED: list[NewsItem] = [
    _item("Reuters", "RELIANCE Q2 profit beats estimates on refining strength", "RELIANCE", Decimal("0.42"), "https://fake.news/1", 20),
    _item("ET Markets", "TCS signs multi-year deal with European bank", "TCS", Decimal("0.31"), "https://fake.news/2", 45),
    _item("Moneycontrol", "HDFCBANK posts record quarterly earnings", "HDFCBANK", Decimal("0.55"), "https://fake.news/3", 75),
    _item("Reuters", "INFY guides lower on weak discretionary demand", "INFY", Decimal("-0.38"), "https://fake.news/4", 90),
    _item("ET Markets", "RELIANCE retail arm expands store network", "RELIANCE", None, "https://fake.news/5", 130),
]


class FakeNewsProvider:
    """Deterministic provider returning canned headlines per symbol."""

    provider_name = "fake"

    def fetch_latest(
        self,
        *,
        symbols: list[str],
        limit: int,
        published_after: datetime | None = None,
    ) -> list[NewsItem]:
        wanted = set(symbols)
        rows = [row for row in _CANNED if row.symbols & wanted]
        if published_after is not None:
            rows = [row for row in rows if row.published_at >= published_after]
        return rows[:limit]

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "provider": self.provider_name,
            "note": "Fake provider — canned headlines.",
        }
