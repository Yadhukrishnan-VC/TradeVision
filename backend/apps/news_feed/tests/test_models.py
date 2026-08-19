"""NEWS-FEED-1 — NewsItem model tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from django.db import IntegrityError, transaction

from apps.news_feed.infrastructure.models import NewsItem

pytestmark = pytest.mark.django_db


def _row(source: str = "Reuters", url: str = "https://example.com/a") -> NewsItem:
    return NewsItem.objects.create(
        provider_id="uuid-1",
        source=source,
        headline="Sample headline",
        url=url,
        published_at=datetime.now(timezone.utc),
        symbols=["RELIANCE"],
        sentiment_score="0.42",
    )


class TestNewsItemModel:
    def test_create_roundtrip(self) -> None:
        row = _row()
        fetched = NewsItem.objects.get(pk=row.pk)
        assert fetched.source == "Reuters"
        assert fetched.symbols == ["RELIANCE"]
        assert fetched.sentiment_score is not None

    def test_unique_constraint_on_source_and_url(self) -> None:
        _row()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                _row(url="https://example.com/a")
        assert NewsItem.objects.count() == 1

    def test_same_url_different_source_is_allowed(self) -> None:
        _row(source="Reuters")
        _row(source="ET Markets")
        assert NewsItem.objects.count() == 2

    def test_sentiment_fields_are_nullable(self) -> None:
        row = NewsItem.objects.create(
            source="Reuters",
            headline="No sentiment supplied",
            url="https://example.com/none",
            published_at=datetime.now(timezone.utc),
            symbols=[],
        )
        assert row.sentiment_score is None
        assert row.sentiment_label is None

    def test_soft_delete_manager(self) -> None:
        row = _row()
        row.delete()
        assert NewsItem.objects.count() == 0
        assert NewsItem.all_objects.count() == 1
