"""NEWS-FEED-1 — API serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.news_feed.infrastructure.models import NewsItem


class NewsItemSerializer(serializers.ModelSerializer):
    sentiment_score = serializers.SerializerMethodField()

    class Meta:
        model = NewsItem
        fields = [
            "id",
            "source",
            "headline",
            "body",
            "url",
            "published_at",
            "ingested_at",
            "symbols",
            "sentiment_score",
            "sentiment_label",
        ]
        read_only_fields = fields

    def get_sentiment_score(self, obj: NewsItem) -> str | None:
        # Decimals stay strings (per the API contract convention); NULL = the
        # provider returned no score → render `--` client-side.
        if obj.sentiment_score is None:
            return None
        return str(obj.sentiment_score)
