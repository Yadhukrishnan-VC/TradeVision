"""NEWS-FEED-1 — news domain event publisher.

Publishes ``news.NewsIngested`` per stored item so other apps can consume
ingested headlines (the audit log's wildcard subscription records it
automatically). Follows the ``orders.*`` publisher pattern from
``apps/execution/infrastructure/event_publishers.py``.
"""

from __future__ import annotations

import uuid
from typing import Any

from apps.eventbus.application.ports import EventBus
from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.news_feed.domain.entities import NewsItem


class NewsEventPublisher:
    """Publish the ``news.NewsIngested`` event for a stored item."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._bus = event_bus or get_event_bus()

    def publish_ingested(
        self,
        item: NewsItem,
        *,
        correlation_id: str | uuid.UUID = "",
    ) -> DomainEvent:
        cid = correlation_id or uuid.uuid4()
        if isinstance(cid, str):
            cid = uuid.UUID(cid)

        payload: dict[str, Any] = {
            "news_id": str(item.id) if item.id else "",
            "source": item.source,
            "headline": item.headline,
            "url": item.url,
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "symbols": sorted(item.symbols),
            "sentiment_score": (
                str(item.sentiment_score) if item.sentiment_score is not None else None
            ),
        }
        event = DomainEvent.create(
            event_type="news.NewsIngested",
            payload=payload,
            correlation_id=cid,
        )
        self._bus.publish(event)
        return event
