from __future__ import annotations

from django.db import models


class StoredEventManager(models.Manager):
    """Custom manager that prevents updates and deletes on StoredEvent."""

    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset()

    def update(self, **kwargs: object) -> int:
        raise NotImplementedError("StoredEvent is append-only; updates are not allowed")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise NotImplementedError("StoredEvent is append-only; deletes are not allowed")


class StoredEvent(models.Model):
    """Append-only event store: the durable source of truth for all domain events.

    This table is the system of record for every published domain event.
    Rows are never updated or deleted by application code — enforcement
    is at the manager level. A defense-in-depth DB-level REVOKE on
    UPDATE/DELETE is recommended for production deployments.
    """

    event_id = models.UUIDField(primary_key=True)
    event_type = models.CharField(max_length=255, db_index=True)
    occurred_at = models.DateTimeField(db_index=True)
    payload = models.JSONField()
    version = models.IntegerField()
    correlation_id = models.UUIDField(db_index=True)
    causation_id = models.UUIDField(null=True, blank=True)
    mirrored_to_stream = models.BooleanField(default=False)

    objects = StoredEventManager()

    class Meta:
        db_table = "eventbus_storedevent"
        indexes = [
            models.Index(fields=["correlation_id", "occurred_at"]),
            models.Index(fields=["event_type", "occurred_at"]),
        ]
        verbose_name = "Stored Event"
        verbose_name_plural = "Stored Events"

    def __str__(self) -> str:
        return f"{self.event_type}[{self.event_id}]"


class ProcessedEvent(models.Model):
    """Deduplication table for at-most-once handler processing.

    Records every (event_id, consumer_group) pair that has been
    successfully processed, enabling idempotent handler execution
    even under at-least-once transport delivery.
    """

    event_id = models.UUIDField()
    consumer_group = models.CharField(max_length=255)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "eventbus_processedevent"
        constraints = [
            models.UniqueConstraint(
                fields=["event_id", "consumer_group"],
                name="uq_processed_event_consumer",
            )
        ]
        indexes = [
            models.Index(fields=["event_id", "consumer_group"]),
        ]
        verbose_name = "Processed Event"
        verbose_name_plural = "Processed Events"

    def __str__(self) -> str:
        return f"{self.event_id}/{self.consumer_group}"


class DeadLetterEvent(models.Model):
    """Records events that exceeded their retry limit.

    After the maximum number of retry attempts is exhausted for a
    given event handler, a DeadLetterEvent row is created so that
    operational tooling can inspect and replay failed events.
    """

    event_id = models.UUIDField()
    event_type = models.CharField(max_length=255)
    consumer_group = models.CharField(max_length=255)
    payload = models.JSONField()
    failure_reason = models.TextField()
    attempts = models.IntegerField()
    failed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "eventbus_deadletterevent"
        indexes = [
            models.Index(fields=["event_type", "failed_at"]),
        ]
        verbose_name = "Dead Letter Event"
        verbose_name_plural = "Dead Letter Events"

    def __str__(self) -> str:
        return f"{self.event_type}[{self.event_id}] ({self.attempts} attempts)"
