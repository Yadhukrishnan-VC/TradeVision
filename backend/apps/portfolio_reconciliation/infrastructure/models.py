"""PORTFOLIO-RECONCILE-1 — Django ORM models.

``DriftRecord`` is an append-only detection log: one row per detected
divergence between the dashboard read model and its source of truth. It is
deliberately NOT a current-state table (no uniqueness on
``(account_id, entity_key)``) so the history of repeated drift on a key is
preserved for pattern analysis — mirroring ``apps.journal``'s append-only
convention.
"""

from __future__ import annotations

from django.db import models

from apps.portfolio_reconciliation.domain.value_objects import (
    DriftClassification,
    EntityType,
)
from core.models import BaseModel


class DriftRecord(BaseModel):
    """One detected read-model divergence from the source of truth."""

    account_id = models.UUIDField(db_index=True)
    entity_type = models.CharField(max_length=16, choices=EntityType.choices())
    entity_key = models.CharField(max_length=128)  # "<account_id>:<symbol>" | order_id
    classification = models.CharField(
        max_length=32,
        choices=DriftClassification.choices(),
    )
    expected_snapshot = models.JSONField(default=dict, blank=True)
    actual_snapshot = models.JSONField(default=dict, blank=True)
    auto_repaired = models.BooleanField(default=False)
    detected_at = models.DateTimeField(db_index=True)
    repaired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "portfolio_reconciliation_driftrecord"
        verbose_name = "Drift Record"
        verbose_name_plural = "Drift Records"
        indexes = [
            models.Index(fields=["account_id", "classification", "-detected_at"]),
            models.Index(fields=["entity_type", "-detected_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"DriftRecord({self.entity_type}/{self.entity_key} "
            f"-> {self.classification})"
        )
