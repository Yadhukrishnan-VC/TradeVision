"""NEWS-FEED-1 — ingestion service, news-context service, provider + budget tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.test import override_settings

from apps.news_feed.application.ingestion_service import NewsIngestionService
from apps.news_feed.application.news_context_service import NewsContextService
from apps.news_feed.domain.entities import NewsItem
from apps.news_feed.domain.exceptions import NewsProviderRateLimited
from apps.news_feed.infrastructure.providers.marketaux_provider import (
    MarketauxNewsProvider,
)
from apps.news_feed.infrastructure.rate_budget import (
    CacheDailyCallBudget,
    InMemoryDailyCallBudget,
)
from core.events.event_types import AggregateSentiment, NewsContext

pytestmark = pytest.mark.django_db


def _item(
    source: str = "Reuters",
    url: str = "https://example.com/a",
    symbol: str = "RELIANCE",
    score: Decimal | None = Decimal("0.42"),
    age_minutes: int = 10,
) -> NewsItem:
    return NewsItem(
        source=source,
        headline=f"{symbol} headline",
        body="summary",
        url=url,
        published_at=datetime.now(timezone.utc) - timedelta(minutes=age_minutes),
        provider_id=f"uuid-{url}",
        symbols=frozenset({symbol}),
        sentiment_score=score,
        sentiment_label=None,
    )


class _RecordingPublisher:
    def __init__(self) -> None:
        self.published: list[object] = []

    def publish_ingested(self, item: NewsItem, *, correlation_id: str = "") -> object:
        self.published.append(item)
        return None


class _StaticProvider:
    provider_name = "static"

    def __init__(self, items: list[NewsItem] | None = None, error: Exception | None = None) -> None:
        self._items = items or []
        self._error = error
        self.calls = 0

    def fetch_latest(self, *, symbols, limit, published_after=None) -> list[NewsItem]:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return [i for i in self._items if i.published_at >= (published_after or datetime.min.replace(tzinfo=timezone.utc))][:limit]

    def health_check(self) -> dict:
        return {"status": "healthy", "provider": self.provider_name}


class TestNewsIngestionService:
    def test_no_symbols_skips_without_calling_provider(self) -> None:
        provider = _StaticProvider([_item()])
        service = NewsIngestionService(
            provider=provider,
            repository=_RepoStub(),
            budget=InMemoryDailyCallBudget(daily_cap=100),
            poll_symbols=[],
            articles_per_request=3,
            lookback_minutes=60,
        )
        summary = service.run()
        assert summary["skipped"] == "no_symbols"
        assert provider.calls == 0

    def test_budget_exhaustion_skips_without_calling_provider(self) -> None:
        provider = _StaticProvider([_item()])
        service = NewsIngestionService(
            provider=provider,
            repository=_RepoStub(),
            budget=InMemoryDailyCallBudget(daily_cap=0),
            poll_symbols=["RELIANCE"],
            articles_per_request=3,
            lookback_minutes=60,
        )
        summary = service.run()
        assert summary["skipped"] == "rate_limit"
        assert provider.calls == 0

    def test_run_stores_items_and_publishes_per_item(self, db) -> None:
        from apps.news_feed.infrastructure.repositories import NewsItemRepository

        publisher = _RecordingPublisher()
        service = NewsIngestionService(
            provider=_StaticProvider([_item(), _item(url="https://example.com/b")]),
            repository=NewsItemRepository(),
            budget=InMemoryDailyCallBudget(daily_cap=100),
            poll_symbols=["RELIANCE"],
            articles_per_request=3,
            lookback_minutes=60,
            publisher=publisher,
        )
        summary = service.run()
        assert summary["inserted"] == 2
        assert len(publisher.published) == 2

    def test_rerun_is_idempotent(self, db) -> None:
        from apps.news_feed.infrastructure.repositories import NewsItemRepository

        publisher = _RecordingPublisher()
        service = NewsIngestionService(
            provider=_StaticProvider([_item(), _item(url="https://example.com/b")]),
            repository=NewsItemRepository(),
            budget=InMemoryDailyCallBudget(daily_cap=100),
            poll_symbols=["RELIANCE"],
            articles_per_request=3,
            lookback_minutes=60,
            publisher=publisher,
        )
        first = service.run()
        second = service.run()
        assert first["inserted"] == 2
        assert second["inserted"] == 0
        assert second["fetched"] == 2
        assert len(publisher.published) == 2

    def test_provider_rate_limit_propagates(self) -> None:
        service = NewsIngestionService(
            provider=_StaticProvider(
                error=NewsProviderRateLimited("Marketaux rate limit (429)")
            ),
            repository=_RepoStub(),
            budget=InMemoryDailyCallBudget(daily_cap=100),
            poll_symbols=["RELIANCE"],
            articles_per_request=3,
            lookback_minutes=60,
        )
        with pytest.raises(NewsProviderRateLimited):
            service.run()


class _RepoStub:
    def upsert_many(self, items):
        return []

    def recent_for_symbol(self, symbol, *, limit, published_after=None):
        return []

    def count(self):
        return 0


class TestNewsContextService:
    def test_empty_store_returns_checked_empty_context(self, db) -> None:
        from apps.news_feed.infrastructure.repositories import NewsItemRepository

        service = NewsContextService(
            repository=NewsItemRepository(),
            lookback_minutes=60,
            max_headlines=5,
        )
        context, checked = service.build("RELIANCE")
        assert checked is True
        assert context.headlines == ()
        assert context.aggregate_sentiment == AggregateSentiment.NEUTRAL

    def test_store_unavailable_returns_unchecked(self, db, monkeypatch) -> None:
        class _BrokenRepo:
            def recent_for_symbol(self, *args, **kwargs):
                raise RuntimeError("DB down")

        service = NewsContextService(
            repository=_BrokenRepo(),
            lookback_minutes=60,
            max_headlines=5,
        )
        context, checked = service.build("RELIANCE")
        assert checked is False
        assert context == NewsContext()

    def test_populated_store_maps_headlines(self, db) -> None:
        from apps.news_feed.infrastructure.models import NewsItem as NewsItemModel
        from apps.news_feed.infrastructure.repositories import NewsItemRepository

        NewsItemModel.objects.create(
            source="Reuters",
            headline="RELIANCE profit beats",
            url="https://example.com/1",
            published_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            symbols=["RELIANCE"],
            sentiment_score="0.42",
        )
        service = NewsContextService(
            repository=NewsItemRepository(),
            lookback_minutes=60,
            max_headlines=5,
        )
        context, checked = service.build("RELIANCE")
        assert checked is True
        assert len(context.headlines) == 1
        item = context.headlines[0]
        assert item.source == "Reuters"
        assert item.sentiment == AggregateSentiment.POSITIVE
        assert context.aggregate_sentiment == AggregateSentiment.POSITIVE

    def test_aggregate_mixed_when_both_sides_present(self) -> None:
        from apps.news_feed.infrastructure.models import NewsItem as NewsItemModel
        from apps.news_feed.infrastructure.repositories import NewsItemRepository

        now = datetime.now(timezone.utc)
        NewsItemModel.objects.create(
            source="Reuters",
            headline="upbeat", url="https://example.com/up",
            published_at=now, symbols=["RELIANCE"], sentiment_score="0.60",
        )
        NewsItemModel.objects.create(
            source="ET Markets",
            headline="downgrade", url="https://example.com/down",
            published_at=now, symbols=["RELIANCE"], sentiment_score="-0.60",
        )
        service = NewsContextService(
            repository=NewsItemRepository(),
            lookback_minutes=60,
            max_headlines=5,
        )
        context, checked = service.build("RELIANCE")
        assert checked is True
        assert context.aggregate_sentiment == AggregateSentiment.MIXED

    def test_missing_score_maps_to_neutral_absence(self) -> None:
        from apps.news_feed.infrastructure.models import NewsItem as NewsItemModel
        from apps.news_feed.infrastructure.repositories import NewsItemRepository

        NewsItemModel.objects.create(
            source="Reuters",
            headline="no score", url="https://example.com/none",
            published_at=datetime.now(timezone.utc), symbols=["RELIANCE"],
        )
        service = NewsContextService(
            repository=NewsItemRepository(),
            lookback_minutes=60,
            max_headlines=5,
        )
        context, checked = service.build("RELIANCE")
        assert checked is True
        assert context.headlines[0].sentiment == AggregateSentiment.NEUTRAL
        assert context.aggregate_sentiment == AggregateSentiment.NEUTRAL


class TestMarketauxProvider:
    def test_parse_articles(self) -> None:
        payload = {
            "meta": {"found": 2, "returned": 2, "limit": 3, "page": 1},
            "data": [
                {
                    "uuid": "art-1",
                    "title": "RELIANCE Q2 profit",
                    "description": "Refining strength drives earnings.",
                    "url": "https://example.com/art1",
                    "published_at": "2026-08-17T06:00:00Z",
                    "source": "Reuters",
                    "entities": [{"symbol": "RELIANCE", "sentiment_score": 0.42}],
                },
                {
                    "uuid": "art-2",
                    "title": "TCS lands deal",
                    "url": "https://example.com/art2",
                    "published_at": "2026-08-17T05:30:00+00:00",
                    "source": "ET Markets",
                    "entities": [{"symbol": "TCS", "sentiment_score": 0.0}],
                },
            ],
        }
        provider = MarketauxNewsProvider()
        items = provider._parse_articles(payload["data"])
        assert len(items) == 2
        assert items[0].source == "Reuters"
        assert items[0].symbols == frozenset({"RELIANCE"})
        assert items[0].sentiment_score == Decimal("0.42")
        assert items[1].symbols == frozenset({"TCS"})

    def test_parse_skips_article_without_url_or_source(self) -> None:
        provider = MarketauxNewsProvider()
        items = provider._parse_articles(
            [
                {"uuid": "x", "title": "no url", "published_at": "2026-08-17T06:00:00Z"},
                {"uuid": "y", "title": "ok", "url": "https://example.com/y", "published_at": "2026-08-17T06:00:00Z", "source": "Reuters"},
            ]
        )
        assert len(items) == 1
        assert items[0].provider_id == "y"


class _FakeResponse:
    def __init__(self, status_code, headers=None, text="", payload=None) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class TestMarketauxProviderHTTP:
    @override_settings(NEWS_API_KEY="test-key")
    def test_429_raises_rate_limited(self, monkeypatch) -> None:
        provider = MarketauxNewsProvider()

        def _get(url, params, timeout):
            return _FakeResponse(429, {"X-RateLimit-Limit": "100", "X-RateLimit-Remaining": "0"})

        monkeypatch.setattr("apps.news_feed.infrastructure.providers.marketaux_provider.requests.get", _get)
        with pytest.raises(NewsProviderRateLimited):
            provider.fetch_latest(symbols=["RELIANCE"], limit=3)

    @override_settings(NEWS_API_KEY="test-key")
    def test_402_raises_rate_limited(self, monkeypatch) -> None:
        provider = MarketauxNewsProvider()

        def _get(url, params, timeout):
            return _FakeResponse(402)

        monkeypatch.setattr("apps.news_feed.infrastructure.providers.marketaux_provider.requests.get", _get)
        with pytest.raises(NewsProviderRateLimited):
            provider.fetch_latest(symbols=["RELIANCE"], limit=3)

    @override_settings(NEWS_API_KEY="test-key")
    def test_remaining_zero_raises_rate_limited(self, monkeypatch) -> None:
        provider = MarketauxNewsProvider()

        def _get(url, params, timeout):
            return _FakeResponse(200, {"X-RateLimit-Remaining": "0"}, payload={"meta": {}, "data": []})

        monkeypatch.setattr("apps.news_feed.infrastructure.providers.marketaux_provider.requests.get", _get)
        with pytest.raises(NewsProviderRateLimited):
            provider.fetch_latest(symbols=["RELIANCE"], limit=3)

    @override_settings(NEWS_API_KEY="")
    def test_missing_api_key_raises_provider_error(self) -> None:
        provider = MarketauxNewsProvider()
        with pytest.raises(Exception):
            provider.fetch_latest(symbols=["RELIANCE"], limit=3)


class TestCacheDailyCallBudget:
    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            }
        }
    )
    def test_budget_exhausts_after_daily_cap(self) -> None:
        cache.clear()
        budget = CacheDailyCallBudget(daily_cap=3)
        assert budget.try_reserve() is True
        assert budget.try_reserve() is True
        assert budget.try_reserve() is True
        assert budget.try_reserve() is False
        assert budget.used_today() == 3
        cache.clear()
