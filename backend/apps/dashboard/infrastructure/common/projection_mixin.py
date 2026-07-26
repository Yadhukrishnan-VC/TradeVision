from __future__ import annotations

from django.db import models


class ProjectionMetadataMixin(models.Model):
    projection_version: int = models.IntegerField(default=0)
    projection_updated_at = models.DateTimeField(null=True, blank=True)
    last_event_id = models.UUIDField(null=True, blank=True)
    last_event_version: int = models.IntegerField(default=0)

    class Meta:
        abstract = True
