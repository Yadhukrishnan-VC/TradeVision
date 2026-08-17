"""NEWS-FEED-1 — Marketaux news provider.

Fetches the latest India-equities news via the licensed Marketaux API
(ADR-029). Endpoint ``GET /v1/news/all``:

- ``symbols`` — comma-separated entity symbols identified in articles
  (e.g. ``RELIANCE,TCS``); ``filter_entities=true`` keeps only matching
  entities; ``must_have_entities=true`` drops untagged articles.
- ``countries=in`` — restrict to entities on Indian exchanges (NSE/BSE).
- Response: ``{meta: {found, returned, limit, page}, data: [NewsArticle]}``.
- Each article carries ``uuid``, ``title``, ``description``, ``url``,
  ``published_at``, ``source``, and ``entities[]`` with ``symbol`` and
  ``sentiment_score`` (range [-1, 1], 0 = neutral; provided on all plans).

Rate limits: ``429`` = too many requests in the past 60s (the limit is echoed
in the ``X-RateLimit-Limit`` header); ``402`` = daily usage quota reached.
Both raise ``NewsProviderRateLimited`` so the ingestion task retries with
backoff. ``X-RateLimit-Remaining: 0`` is also treated as rate-limited.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import requests

from apps.news_feed.domain.entities import NewsItem
from apps.news_feed.domain.exceptions import (
    NewsProviderError,
    NewsProviderRateLimited,
)
from core.config import config

logger = logging.getLogger(__name__)

_NEWS_ALL_ENDPOINT = "/news/all"


class MarketauxNewsProvider:
    """Fetch the latest news for the configured symbols from Marketaux."""

    provider_name = "marketaux"

    def fetch_latest(
        self,
        *,
        symbols: list[str],
        limit: int,
        published_after: datetime | None = None,
    ) -> list[NewsItem]:
        api_token = config.news_api_key
        if not api_token:
            raise NewsProviderError(
                "NEWS_API_KEY is not configured; cannot fetch market news."
            )

        params: dict[str, Any] = {
            "api_token": api_token,
            "symbols": ",".join(symbols),
            "filter_entities": "true",
            "must_have_entities": "true",
            "countries": "in",
            "language": "en",
            "limit": max(limit, 1),
            "group_similar": "false",
        }
        if published_after is not None:
            params["published_after"] = published_after.isoformat()

        started = time.monotonic()
        try:
            response = requests.get(
                self._build_url(),
                params=params,
                timeout=config.news_request_timeout_seconds,
            )
        except requests.RequestException as exc:
            raise NewsProviderError(f"Marketaux request failed: {exc}") from exc

        if response.status_code in (429, 402) or _remaining_zero(response):
            raise NewsProviderRateLimited(
                f"Marketaux rate limit ({response.status_code}): "
                f"limit={response.headers.get('X-RateLimit-Limit')} "
                f"remaining={response.headers.get('X-RateLimit-Remaining')}"
            )
        try:
            response.raise_for_status()
            payload = response.json()
        except requests.HTTPError as exc:
            raise NewsProviderError(
                f"Marketaux returned HTTP {response.status_code}: {response.text[:200]}"
            ) from exc
        except ValueError as exc:
            raise NewsProviderError(
                f"Marketaux returned non-JSON response: {exc}"
            ) from exc

        articles = payload.get("data", []) if isinstance(payload, dict) else []
        parsed = self._parse_articles(articles)
        logger.info(
            "marketaux_news_fetched",
            extra={
                "count": len(parsed),
                "symbols": symbols,
                "latency_ms": round((time.monotonic() - started) * 1000, 2),
            },
        )
        return parsed

    def health_check(self) -> dict[str, Any]:
        if not config.news_api_key:
            return {
                "status": "degraded",
                "provider": self.provider_name,
                "note": "NEWS_API_KEY not configured.",
            }
        return {
            "status": "healthy",
            "provider": self.provider_name,
            "note": "Marketaux API key configured.",
        }

    def _build_url(self) -> str:
        base = config.news_api_base_url.rstrip("/")
        return f"{base}{_NEWS_ALL_ENDPOINT}"

    @staticmethod
    def _parse_articles(articles: list[dict[str, Any]]) -> list[NewsItem]:
        parsed: list[NewsItem] = []
        for article in articles:
            try:
                published_at = _parse_datetime(article.get("published_at"))
                url = str(article.get("url") or "").strip()
                source = str(article.get("source") or "").strip()
                if not url or not source:
                    continue
                symbols, score = _parse_entities(article.get("entities") or [])
                parsed.append(
                    NewsItem(
                        source=source,
                        headline=str(article.get("title") or "").strip(),
                        body=str(article.get("description") or article.get("snippet") or "").strip() or None,
                        url=url,
                        published_at=published_at,
                        provider_id=str(article.get("uuid") or "").strip(),
                        symbols=frozenset(symbols),
                        sentiment_score=score,
                        sentiment_label=None,
                    )
                )
            except (ValueError, TypeError, KeyError) as exc:
                logger.warning(
                    "marketaux_article_skipped",
                    extra={"error": str(exc), "article": article},
                )
        return parsed


def _parse_entities(entities: list[dict[str, Any]]) -> tuple[list[str], Decimal | None]:
    """Extract symbols + the first available sentiment score from entities."""
    symbols: list[str] = []
    score: Decimal | None = None
    for entity in entities:
        symbol = str(entity.get("symbol") or "").strip().upper()
        if symbol:
            symbols.append(symbol)
        raw_score = entity.get("sentiment_score")
        if score is None and raw_score is not None:
            try:
                score = Decimal(str(raw_score))
            except (InvalidOperation, ValueError, TypeError):
                score = None
    return symbols, score


def _parse_datetime(raw: Any) -> datetime:
    if raw is None:
        raise ValueError("article missing published_at")
    value = str(raw)
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _remaining_zero(response: requests.Response) -> bool:
    remaining = response.headers.get("X-RateLimit-Remaining")
    if remaining is None:
        return False
    try:
        return int(remaining) <= 0
    except ValueError:
        return False
