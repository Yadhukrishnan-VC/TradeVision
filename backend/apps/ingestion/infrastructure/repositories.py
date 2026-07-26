from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from apps.ingestion.domain.value_objects import WebhookSource
from apps.ingestion.infrastructure.models import RawWebhookEvent

logger = logging.getLogger(__name__)


class RawWebhookEventRepository:
    """Repository for ``RawWebhookEvent`` persistence and queries."""

    def create(
        self,
        source: str,
        raw_body: dict[str, Any],
        headers: dict[str, Any] | None = None,
        signature_valid: bool = False,
    ) -> RawWebhookEvent:
        """Persist a new raw webhook event.

        Args:
            source:          Webhook source (``"tradingview"`` or ``"chartink"``).
            raw_body:        The parsed payload as a dict.
            headers:         HTTP headers from the request (optional).
            signature_valid: Whether the request signature was verified.

        Returns:
            The newly created ``RawWebhookEvent`` instance.
        """
        return RawWebhookEvent.objects.create(
            source=source,
            raw_body=raw_body,
            headers=headers or {},
            signature_valid=signature_valid,
        )

    def find_unprocessed(
        self,
        older_than_minutes: int = 2,
        limit: int = 100,
    ) -> list[RawWebhookEvent]:
        """Return unprocessed events older than the specified threshold.

        Args:
            older_than_minutes: Age threshold in minutes.
            limit:              Maximum number of events to return.

        Returns:
            List of unprocessed ``RawWebhookEvent`` instances.
        """
        cutoff = datetime.now(tz=__import__("django").utils.timezone.now().tzinfo) - timedelta(
            minutes=older_than_minutes,
        )

        return list(
            RawWebhookEvent.objects.filter(
                processed=False,
                received_at__lte=cutoff,
            )[:limit]
        )

    def mark_processed(self, event_id: uuid) -> None:
        """Mark a raw webhook event as processed.

        Args:
            event_id: The UUID of the event to mark.
        """
        RawWebhookEvent.objects.filter(pk=event_id).update(processed=True)

    def count_unprocessed(self) -> int:
        """Return the number of unprocessed webhook events."""
        return RawWebhookEvent.objects.filter(processed=False).count()
