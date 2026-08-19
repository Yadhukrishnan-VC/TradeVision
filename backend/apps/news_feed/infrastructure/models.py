"""NEWS-FEED-1 — Django ORM models.

``NewsItem`` is the ingested-news store. One row exists per article as
identified by the ``(source, url)`` natural key; the unique constraint is the
idempotency guard for repeated ingestion runs (a re-poll of the same article
is a no-op, never a duplicate row).

Sentiment discipline (ADR-029 §2): ``sentiment_score`` is nullable and only
ever carries a provider-supplied score; ``sentiment_label`` is nullable and
stays ``None`` until a real sentiment-label model lands (a future batch) —
the frontend renders ``--`` for it.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone

from core.models import BaseModel


class NewsItem(BaseModel):
    """A single ingested news headline with provider metadata."""

    provider_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Provider-side article id (Marketaux 'uuid'); empty when absent.",
    )
    source = models.CharField(
        max_length=128,
        db_index=True,
        help_text="Publication/feed name (e.g. 'Reuters').",
    )
    headline = models.TextField(help_text="Article title.")
    body = models.TextField(
        blank=True,
        default="",
        help_text="Article summary/body snippet when the provider returns one.",
    )
    url = models.URLField(
        max_length=2048,
        db_index=True,
        help_text="Canonical article URL — part of the (source, url) dedup key.",
    )
    published_at = models.DateTimeField(
        db_index=True,
        help_text="When the provider says the article was published.",
    )
    ingested_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="When TradeVision stored this row.",
    )
    symbols = models.JSONField(
        default=list,
        help_text="Symbols the provider identified in the article (e.g. ['RELIANCE']).",
    )
    sentiment_score = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Provider-supplied sentiment in [-1, 1]; NULL = provider returned none.",
    )
    sentiment_label = models.CharField(
        max_length=16,
        null=True,
        blank=True,
        help_text="NULL in this batch — no provider returns a label; not hand-rolled.",
    )

    class Meta:
        db_table = "news_feed_newsitem"
        verbose_name = "News Item"
        verbose_name_plural = "News Items"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "url"],
                name="uniq_newsitem_source_url",
            ),
        ]
        indexes = [
            models.Index(
                fields=["published_at"],
                name="newsitem_published_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"NewsItem({self.source} · {self.headline[:40]})"
