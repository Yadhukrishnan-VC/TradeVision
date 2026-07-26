from __future__ import annotations

from django.db import models


class TimestampedModel(models.Model):
    """Abstract base model providing auto-managed created_at and updated_at fields."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
