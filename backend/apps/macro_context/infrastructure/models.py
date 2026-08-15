"""MACRO-CONTEXT-1 — Django ORM models.

``MacroObservation`` is an append-only provenance store. One row exists per
(provider, series_id, observed_at, published_at): every FRED revision is a
new row, never an UPDATE, so the full point-in-time history is preserved.
The natural-key unique constraint doubles as the idempotency guard for
repeated ingestion runs.

``value`` is nullable: ``NULL`` means "known missing at publish time"
(FRED ``"."``) — never a zero.
"""

from __future__ import annotations

from django.db import models

from core.models import BaseModel


class MacroObservation(BaseModel):
    """A single macro value plus the moment it became public."""

    provider = models.CharField(max_length=32)
    series_id = models.CharField(max_length=32, db_index=True)
    observed_at = models.DateField()
    published_at = models.DateTimeField()
    value = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="NULL = known missing (FRED '.'), never zero.",
    )

    class Meta:
        db_table = "macro_context_macroobservation"
        verbose_name = "Macro Observation"
        verbose_name_plural = "Macro Observations"
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "series_id", "observed_at", "published_at"],
                name="uniq_macro_observation_vintage",
            ),
        ]
        indexes = [
            models.Index(
                fields=["series_id", "observed_at", "published_at"],
                name="macro_obs_pit_idx",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"MacroObservation({self.provider}/{self.series_id} "
            f"@{self.observed_at} pub {self.published_at:%Y-%m-%d} "
            f"= {self.value})"
        )
