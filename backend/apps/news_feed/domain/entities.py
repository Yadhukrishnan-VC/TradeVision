"""NEWS-FEED-1 — pure domain entities.

``NewsItem`` is the unit of ingested news: a single headline from a licensed
provider, tagged with the symbols the provider identified in it. Nothing in
this module touches Django ORM models.

Sentiment discipline (ADR-029 §2): ``sentiment_score`` is nullable and is
populated ONLY from a provider-supplied score — it is never computed locally.
``sentiment_label`` is always ``None`` in this batch because no provider
returns a label and hand-rolling score→label mapping is a separate future
batch (a real sentiment model).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class NewsItem:
    """A single ingested news headline with provider metadata.

    - ``source``: publication/feed name (e.g. ``"Reuters"``).
    - ``headline``: the article title.
    - ``url``: canonical article URL — together with ``source`` it forms the
      natural dedup key for ingestion.
    - ``provider_id``: the provider's own article id (Marketaux ``uuid``);
      empty when the provider has none.
    - ``published_at``: when the provider says the article was published.
    - ``symbols``: the symbols the provider identified in the article
      (e.g. ``{"RELIANCE", "TCS"}``); empty when none were tagged.
    - ``sentiment_score``: provider-supplied score in [−1, 1], or ``None``
      when the provider did not return one (never locally computed).
    - ``sentiment_label``: always ``None`` in this batch (see module doc).
    """

    source: str
    headline: str
    url: str
    published_at: datetime
    provider_id: str = ""
    body: str | None = None
    symbols: frozenset[str] = field(default_factory=frozenset)
    sentiment_score: Decimal | None = None
    sentiment_label: str | None = None
    id: UUID | None = None
    ingested_at: datetime | None = None
