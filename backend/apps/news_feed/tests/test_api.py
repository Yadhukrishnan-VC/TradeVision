"""NEWS-FEED-1 — news API integration tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apps.news_feed.infrastructure.models import NewsItem

pytestmark = pytest.mark.django_db

NEWS_PATH = "/api/v1/news/"


def _row(symbol: str = "RELIANCE", source: str = "Reuters", **kwargs) -> NewsItem:
    defaults = {
        "source": source,
        "headline": f"{symbol} headline",
        "url": f"https://example.com/{symbol}-{source}-{datetime.now(timezone.utc).microsecond}",
        "published_at": datetime.now(timezone.utc),
        "symbols": [symbol],
        "sentiment_score": "0.42",
    }
    defaults.update(kwargs)
    return NewsItem.objects.create(**defaults)


class TestNewsListAPI:
    def test_unauthenticated_returns_401(self, api_client) -> None:
        response = api_client.get(NEWS_PATH)
        assert response.status_code == 401

    def test_empty_list_returns_paginated_envelope(self, authenticated_client) -> None:
        response = authenticated_client.get(NEWS_PATH)
        assert response.status_code == 200
        assert set(response.data.keys()) == {"count", "next", "previous", "results"}
        assert response.data["count"] == 0
        assert response.data["results"] == []

    def test_list_returns_ingested_items(self, authenticated_client) -> None:
        _row()
        response = authenticated_client.get(NEWS_PATH)
        assert response.status_code == 200
        assert response.data["count"] == 1
        row = response.data["results"][0]
        assert row["source"] == "Reuters"
        assert row["symbols"] == ["RELIANCE"]
        assert row["sentiment_score"] == "0.4200"
        assert row["sentiment_label"] is None

    def test_pagination_limits_page_size(self, authenticated_client) -> None:
        for i in range(25):
            _row(url=f"https://example.com/{i}")
        response = authenticated_client.get(NEWS_PATH)
        assert response.status_code == 200
        assert response.data["count"] == 25
        assert len(response.data["results"]) == 20
        page_two = authenticated_client.get(NEWS_PATH, {"page": 2})
        assert len(page_two.data["results"]) == 5

    def test_symbol_filter(self, authenticated_client) -> None:
        _row(symbol="RELIANCE")
        _row(symbol="TCS")
        response = authenticated_client.get(NEWS_PATH, {"symbol": "TCS"})
        assert response.status_code == 200
        assert response.data["count"] == 1
        assert response.data["results"][0]["symbols"] == ["TCS"]

    def test_sentiment_null_when_provider_returned_none(self, authenticated_client) -> None:
        _row(sentiment_score=None, sentiment_label=None)
        response = authenticated_client.get(NEWS_PATH)
        row = response.data["results"][0]
        assert row["sentiment_score"] is None
        assert row["sentiment_label"] is None


class TestNewsDetailAPI:
    def test_detail_returns_item(self, authenticated_client) -> None:
        row = _row()
        response = authenticated_client.get(f"{NEWS_PATH}{row.pk}/")
        assert response.status_code == 200
        assert response.data["id"] == str(row.pk)
        assert response.data["source"] == "Reuters"

    def test_detail_missing_returns_404(self, authenticated_client) -> None:
        import uuid

        response = authenticated_client.get(f"{NEWS_PATH}{uuid.uuid4()}/")
        assert response.status_code == 404
