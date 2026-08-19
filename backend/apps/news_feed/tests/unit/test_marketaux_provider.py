"""Marketaux provider failure-path regression tests (NEWS-FEED-1).

Covers the failure modes not exercised by ``test_services.py``:
timeout / connection errors, HTTP error statuses, non-JSON payloads,
malformed articles, and header edge cases. The fetch path is mocked at the
``requests.get`` boundary so no network is involved.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
import requests
from django.test import override_settings

from apps.news_feed.domain.exceptions import NewsProviderError, NewsProviderRateLimited
from apps.news_feed.infrastructure.providers.marketaux_provider import (
    MarketauxNewsProvider,
    _parse_datetime,
    _parse_entities,
    _remaining_zero,
)

pytestmark = pytest.mark.django_db


class _Response:
    def __init__(
        self,
        status_code: int,
        *,
        headers: dict | None = None,
        text: str = "",
        payload=None,
        json_error: bool = False,
        http_error: bool = False,
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text
        self._payload = payload
        self._json_error = json_error
        self._http_error = http_error

    def json(self):
        if self._json_error:
            raise ValueError("Expecting value: line 1 column 1")
        return self._payload

    def raise_for_status(self):
        if self._http_error:
            raise requests.HTTPError(f"HTTP {self.status_code}")


@pytest.fixture
def provider() -> MarketauxNewsProvider:
    return MarketauxNewsProvider()


@pytest.fixture
def fake_get(monkeypatch):
    def _set(fake_response):
        monkeypatch.setattr(
            "apps.news_feed.infrastructure.providers.marketaux_provider.requests.get",
            lambda url, params, timeout: fake_response,
        )

    return _set


class TestTransportFailures:
    @override_settings(NEWS_API_KEY="test-key")
    def test_timeout_raises_provider_error(self, provider, fake_get, monkeypatch) -> None:
        def _raise(url, params, timeout):
            raise requests.Timeout("timed out")

        monkeypatch.setattr(
            "apps.news_feed.infrastructure.providers.marketaux_provider.requests.get",
            _raise,
        )
        with pytest.raises(NewsProviderError) as exc:
            provider.fetch_latest(symbols=["RELIANCE"], limit=3)
        assert "request failed" in str(exc.value)

    @override_settings(NEWS_API_KEY="test-key")
    def test_connection_error_raises_provider_error(self, provider, monkeypatch) -> None:
        def _raise(url, params, timeout):
            raise requests.ConnectionError("connection refused")

        monkeypatch.setattr(
            "apps.news_feed.infrastructure.providers.marketaux_provider.requests.get",
            _raise,
        )
        with pytest.raises(NewsProviderError) as exc:
            provider.fetch_latest(symbols=["RELIANCE"], limit=3)
        assert "request failed" in str(exc.value)

    @override_settings(NEWS_API_KEY="test-key")
    def test_http_500_raises_provider_error(self, provider, fake_get) -> None:
        fake_get(_Response(500, text="internal error", http_error=True))
        with pytest.raises(NewsProviderError) as exc:
            provider.fetch_latest(symbols=["RELIANCE"], limit=3)
        assert "HTTP 500" in str(exc.value)

    @override_settings(NEWS_API_KEY="test-key")
    def test_non_json_body_raises_provider_error(self, provider, fake_get) -> None:
        fake_get(_Response(200, text="<html>not json</html>", json_error=True))
        with pytest.raises(NewsProviderError) as exc:
            provider.fetch_latest(symbols=["RELIANCE"], limit=3)
        assert "non-JSON" in str(exc.value)

    @override_settings(NEWS_API_KEY="test-key")
    def test_payload_not_a_dict_returns_empty(self, provider, fake_get) -> None:
        fake_get(_Response(200, payload=["not", "a", "dict"]))
        items = provider.fetch_latest(symbols=["RELIANCE"], limit=3)
        assert items == []


class TestHeaderEdgeCases:
    def test_remaining_zero_with_non_numeric_header_is_false(self) -> None:
        response = _Response(200, headers={"X-RateLimit-Remaining": "garbage"})
        assert _remaining_zero(response) is False

    def test_remaining_zero_missing_header_is_false(self) -> None:
        response = _Response(200)
        assert _remaining_zero(response) is False

    @override_settings(NEWS_API_KEY="test-key")
    def test_429_with_positive_remaining_still_rate_limited(self, provider, fake_get) -> None:
        fake_get(_Response(429, headers={"X-RateLimit-Remaining": "5"}))
        with pytest.raises(NewsProviderRateLimited):
            provider.fetch_latest(symbols=["RELIANCE"], limit=3)


class TestArticleParsingFailures:
    def test_missing_published_at_skips_article(self, provider) -> None:
        items = provider._parse_articles(
            [
                {
                    "uuid": "bad",
                    "title": "no timestamp",
                    "url": "https://example.com/bad",
                    "source": "Reuters",
                },
                {
                    "uuid": "good",
                    "title": "ok",
                    "url": "https://example.com/good",
                    "published_at": "2026-08-17T06:00:00Z",
                    "source": "Reuters",
                },
            ]
        )
        assert [i.provider_id for i in items] == ["good"]

    def test_invalid_datetime_skips_article(self, provider) -> None:
        items = provider._parse_articles(
            [
                {
                    "uuid": "bad",
                    "title": "bad date",
                    "url": "https://example.com/bad",
                    "published_at": "not-a-date",
                    "source": "Reuters",
                }
            ]
        )
        assert items == []

    def test_invalid_sentiment_score_becomes_none(self, provider) -> None:
        items = provider._parse_articles(
            [
                {
                    "uuid": "art",
                    "title": "ok",
                    "url": "https://example.com/art",
                    "published_at": "2026-08-17T06:00:00Z",
                    "source": "Reuters",
                    "entities": [{"symbol": "RELIANCE", "sentiment_score": "NaN-score"}],
                }
            ]
        )
        assert len(items) == 1
        assert items[0].sentiment_score is None

    def test_entities_skip_empty_symbols(self) -> None:
        symbols, score = _parse_entities(
            [{"symbol": ""}, {"symbol": "  "}, {"symbol": "TCS", "sentiment_score": 0.1}]
        )
        assert symbols == ["TCS"]
        assert score == Decimal("0.1")

    def test_parse_datetime_treats_naive_as_utc(self) -> None:
        parsed = _parse_datetime("2026-08-17T06:00:00")
        assert parsed == datetime(2026, 8, 17, 6, 0, 0, tzinfo=timezone.utc)

    def test_parse_datetime_handles_z_suffix(self) -> None:
        parsed = _parse_datetime("2026-08-17T06:00:00Z")
        assert parsed.tzinfo is not None

    def test_parse_datetime_rejects_none(self) -> None:
        with pytest.raises(ValueError):
            _parse_datetime(None)