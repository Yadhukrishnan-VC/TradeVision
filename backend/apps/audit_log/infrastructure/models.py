from __future__ import annotations

import uuid

from django.db import models

from apps.common.infrastructure.model_mixins import TimestampedModel

ACTOR_CHOICES = [
    ("system", "System"),
    ("user", "User"),
    ("ai", "AI"),
]


class AuditLogEntryManager(models.Manager):
    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset()

    def update(self, **kwargs: object) -> int:
        raise NotImplementedError("AuditLogEntry is append-only; updates are not allowed")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise NotImplementedError("AuditLogEntry is append-only; deletes are not allowed")


class AuditLogEntry(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.CharField(max_length=16, choices=ACTOR_CHOICES)
    action = models.CharField(max_length=255)
    target_type = models.CharField(max_length=255)
    target_id = models.CharField(max_length=255)
    metadata = models.JSONField()
    occurred_at = models.DateTimeField(db_index=True)

    objects = AuditLogEntryManager()

    class Meta:
        db_table = "audit_log_auditlogentry"
        indexes = [
            models.Index(fields=["target_type", "target_id"]),
            models.Index(fields=["occurred_at"]),
        ]
        verbose_name = "Audit Log Entry"
        verbose_name_plural = "Audit Log Entries"

    def __str__(self) -> str:
        return f"{self.action}[{self.id}] by {self.actor}"
