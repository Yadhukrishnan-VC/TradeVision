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


from django.db import models


class EventLogManager(models.Manager):
    def has_been_applied(self, event_id: UUID, projector: str) -> bool:
        return self.filter(event_id=event_id, projector=projector).exists()

    def mark_applied(self, event_id: UUID, projector: str) -> EventLog:
        return self.create(event_id=event_id, projector=projector)


class EventLog(models.Model):
    event_id = models.UUIDField(db_index=True)


class DriftAlertRepository:
    """Repository for querying DriftAlert records from the live_drift app."""

    def list_recent(self, limit: int = 50) -> list[dict]:
        from apps.live_drift.infrastructure.models import DriftAlert
        alerts = DriftAlert.objects.all().order_by("-created_at")[:limit]
        return [
            {
                "alert_id": str(a.id),
                "observed_rule_id": a.observed_rule.rule_id,
                "kind": a.kind,
                "window_trades": a.window_trades,
                "live_expectancy": str(a.live_expectancy),
                "live_win_rate": str(a.live_win_rate),
                "baseline_expectancy": str(a.baseline_expectancy) if a.baseline_expectancy else "—",
                "message": a.message,
                "notified": a.notified,
                "created_at": a.created_at.isoformat(),
            }
            for a in alerts
        ]

    def list_active(self) -> list[dict]:
        from apps.live_drift.infrastructure.models import DriftAlert
        alerts = DriftAlert.objects.filter(notified=False).order_by("-created_at")
        return [
            {
                "alert_id": str(a.id),
                "observed_rule_id": a.observed_rule.rule_id,
                "kind": a.kind,
                "window_trades": a.window_trades,
                "live_expectancy": str(a.live_expectancy),
                "live_win_rate": str(a.live_win_rate),
                "baseline_expectancy": str(a.baseline_expectancy) if a.baseline_expectancy else "—",
                "message": a.message,
                "notified": a.notified,
                "created_at": a.created_at.isoformat(),
            }
            for a in alerts
        ]

    def count_active(self) -> int:
        from apps.live_drift.infrastructure.models import DriftAlert
        return DriftAlert.objects.filter(notified=False).count()
