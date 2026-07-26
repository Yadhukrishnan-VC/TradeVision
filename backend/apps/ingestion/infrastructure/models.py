from __future__ import annotations

import uuid

from django.db import models

from apps.common.infrastructure.model_mixins import TimestampedModel


class RawWebhookEvent(TimestampedModel):
    """Persistent record of an ingested webhook event.

    Every incoming webhook payload is stored here before being published
    as a domain event. This enables debugging, replay, and idempotent
    processing of retried webhooks.

    Indexes:
        - ``source``: Filtering by webhook source.
        - ``received_at``: Time-based queries and retention policies.
        - ``(source, received_at)``: Combined queries for reprocessing.
        - ``processed``: Efficiently finding unprocessed events.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for this webhook event.",
    )
    source = models.CharField(
        max_length=50,
        db_index=True,
        choices=[
            ("tradingview", "TradingView"),
            ("chartink", "Chartink"),
        ],
        help_text="Origin of the webhook payload.",
    )
    raw_body = models.JSONField(
        help_text="The raw webhook payload as a JSON blob.",
    )
    headers = models.JSONField(
        default=dict,
        blank=True,
        help_text="HTTP headers from the original request.",
    )
    signature_valid = models.BooleanField(
        default=False,
        help_text="Whether the request signature was verified successfully.",
    )
    received_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="UTC datetime when this webhook was received.",
    )
    processed = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this event has been published downstream.",
    )

    class Meta:
        app_label = "ingestion"
        db_table = "ingestion_raw_webhook_event"
        verbose_name = "Raw Webhook Event"
        verbose_name_plural = "Raw Webhook Events"
        indexes = [
            models.Index(
                fields=["source", "received_at"],
                name="idx_ingestion_source_received",
            ),
            models.Index(
                fields=["processed", "received_at"],
                name="idx_ingestion_processed",
            ),
        ]

    def __str__(self) -> str:
        return f"RawWebhookEvent({self.source}, {self.received_at})"
