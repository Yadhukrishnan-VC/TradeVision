"""NEWS-FEED-1 — ingestion Celery task tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import Retry
from django.test import override_settings

from apps.news_feed.domain.exceptions import NewsProviderRateLimited
from apps.news_feed.infrastructure.tasks import ingest_news

pytestmark = pytest.mark.django_db


class _RaisingService:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def run(self, *, correlation_id: str = "") -> dict:
        raise self._error


class TestIngestNewsTask:
    @override_settings(NEWS_INGESTION_ENABLED=False)
    def test_disabled_is_noop(self) -> None:
        with patch(
            "apps.news_feed.infrastructure.tasks.get_ingestion_service"
        ) as mock_factory:
            result = ingest_news.apply().get()
            assert result is None
            mock_factory.assert_not_called()

    @override_settings(NEWS_INGESTION_ENABLED=True)
    def test_rate_limited_triggers_retry(self) -> None:
        with (
            patch(
                "apps.news_feed.infrastructure.tasks.get_ingestion_service",
                return_value=_RaisingService(NewsProviderRateLimited("429")),
            ),
            pytest.raises(Retry),
        ):
            ingest_news.apply()

    @override_settings(NEWS_INGESTION_ENABLED=True)
    def test_success_path_returns_none(self) -> None:
        service = MagicMock()
        service.run.return_value = {"fetched": 2, "inserted": 2, "skipped": None, "errors": []}
        with patch(
            "apps.news_feed.infrastructure.tasks.get_ingestion_service",
            return_value=service,
        ):
            result = ingest_news.apply().get()
            assert result is None
            assert service.run.called
