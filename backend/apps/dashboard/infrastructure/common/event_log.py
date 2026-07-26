from __future__ import annotations

from uuid import UUID

from django.db import models


class EventLogManager(models.Manager):
    def has_been_applied(self, event_id: UUID, projector: str) -> bool:
        return self.filter(event_id=event_id, projector=projector).exists()

    def mark_applied(self, event_id: UUID, projector: str) -> EventLog:
        return self.create(event_id=event_id, projector=projector)


class EventLog(models.Model):
    event_id = models.UUIDField(db_index=True)
    projector = models.CharField(max_length=255)
    applied_at = models.DateTimeField(auto_now_add=True)

    objects = EventLogManager()

    class Meta:
        db_table = "dashboard_eventlog"
        constraints = [
            models.UniqueConstraint(
                fields=["event_id", "projector"],
                name="uq_dashboard_eventlog_event_projector",
            ),
        ]
        indexes = [
            models.Index(fields=["event_id", "projector"]),
        ]

    def __str__(self) -> str:
        return f"EventLog({self.event_id}/{self.projector})"
