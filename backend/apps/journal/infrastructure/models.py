from __future__ import annotations

import uuid
from uuid import UUID

from django.db import models

from apps.accounts.infrastructure.models import Account
from apps.common.infrastructure.model_mixins import TimestampedModel


class JournalEventLogManager(models.Manager):
    def has_been_applied(self, event_id: UUID, consumer: str) -> bool:
        return self.filter(event_id=event_id, consumer=consumer).exists()

    def mark_applied(self, event_id: UUID, consumer: str) -> JournalEventLog:
        return self.create(event_id=event_id, consumer=consumer)


class JournalEventLog(models.Model):
    event_id = models.UUIDField(db_index=True)
    consumer = models.CharField(max_length=255)
    applied_at = models.DateTimeField(auto_now_add=True)

    objects = JournalEventLogManager()

    class Meta:
        db_table = "journal_eventlog"
        constraints = [
            models.UniqueConstraint(
                fields=["event_id", "consumer"],
                name="uq_journal_eventlog_event_consumer",
            ),
        ]
        indexes = [
            models.Index(fields=["event_id", "consumer"]),
        ]

    def __str__(self) -> str:
        return f"JournalEventLog({self.event_id}/{self.consumer})"


class JournalEntry(TimestampedModel):
    OUTCOME_CHOICES = [
        ("won", "Won"),
        ("lost", "Lost"),
        ("breakeven", "Breakeven"),
        ("no_trade", "No Trade"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    correlation_id = models.UUIDField(unique=True)
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="journal_entries",
    )
    signal_snapshot = models.JSONField(null=True, blank=True)
    decision_snapshot = models.JSONField(null=True, blank=True)
    order_events = models.JSONField(default=list)
    position_id = models.UUIDField(null=True, blank=True)
    outcome = models.CharField(
        max_length=20,
        choices=OUTCOME_CHOICES,
        null=True,
        blank=True,
    )
    realized_pnl = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
    )
    finalized = models.BooleanField(default=False)
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "journal_journalentry"
        indexes = [
            models.Index(fields=["account", "finalized"]),
        ]

    def __str__(self) -> str:
        status = "finalized" if self.finalized else "pending"
        return f"JournalEntry({self.correlation_id}) [{status}]"
