from __future__ import annotations

import uuid

from django.db import models

from apps.common.infrastructure.model_mixins import TimestampedModel


class HistoricalFeatureVector(TimestampedModel):
    """Precomputed feature vector for one historical trading session.

    Written by the nightly ``precompute_historical_vectors`` Celery task
    (ADR-007 §5.3 — feature vectors are precomputed, never computed at query
    time). The ``features`` JSON payload stores the serialised
    ``FeatureVector`` domain object with Decimal values stored as strings to
    preserve precision (matching the event-payload convention).

    Indexes:
        - ``(symbol, as_of)``: the primary access pattern for query-time
          analogue retrieval.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for this historical feature vector.",
    )
    symbol = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Trading symbol (e.g. RELIANCE).",
    )
    as_of = models.DateField(
        db_index=True,
        help_text="Trading session date (UTC).",
    )
    features = models.JSONField(
        default=dict,
        blank=True,
        help_text="Serialised FeatureVector: Decimal values stored as strings.",
    )
    subsequent_price_change_pct = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Actual % price change over the following session (outcome).",
    )
    subsequent_window_hours = models.IntegerField(
        default=24,
        help_text="Outcome window in hours (default: next trading day).",
    )
    data_sufficiency_note = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Human-readable note about data coverage for this session.",
    )

    class Meta:
        app_label = "pattern_engine"
        db_table = "pattern_engine_historicalfeaturevector"
        verbose_name = "Historical Feature Vector"
        verbose_name_plural = "Historical Feature Vectors"
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "as_of"],
                name="uq_pattern_engine_symbol_asof",
            ),
        ]
        indexes = [
            models.Index(
                fields=["symbol", "as_of"],
                name="idx_pe_symbol_asof",
            ),
        ]
        ordering = ["-as_of"]

    def __str__(self) -> str:
        return f"HistoricalFeatureVector({self.symbol}, {self.as_of})"


class PatternAnalysisRun(TimestampedModel):
    """One persisted Pattern Engine analysis run.

    Stores the rich ``PatternAnalysisResult`` for audit/inspection via the
    REST API and Django admin. The same result is mapped down to the frozen
    ``PatternContext`` contract at publication time.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for this analysis run.",
    )
    symbol = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Trading symbol (e.g. RELIANCE).",
    )
    as_of = models.DateTimeField(
        db_index=True,
        help_text="UTC datetime of the analysed session.",
    )
    top_analogue_summary = models.TextField(
        blank=True,
        default="",
        help_text="Human-readable summary of the top matching analogue.",
    )
    confidence_contribution = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=0,
        help_text="Deterministic confidence contribution in [0, 1].",
    )
    historical_recommendation_accuracy = models.DecimalField(
        max_digits=8,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Trader Memory win rate for the symbol (optional enrichment).",
    )
    matched_patterns = models.JSONField(
        default=list,
        blank=True,
        help_text="Serialised list of MatchedPattern entries.",
    )
    evidence = models.JSONField(
        default=list,
        blank=True,
        help_text="Serialised list of EvidenceItem entries.",
    )
    data_sufficiency_note = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="e.g. 'only 40 days of history available'.",
    )

    class Meta:
        app_label = "pattern_engine"
        db_table = "pattern_engine_patternanalysisrun"
        verbose_name = "Pattern Analysis Run"
        verbose_name_plural = "Pattern Analysis Runs"
        indexes = [
            models.Index(
                fields=["symbol", "as_of"],
                name="idx_pe_run_symbol_asof",
            ),
        ]
        ordering = ["-as_of"]

    def __str__(self) -> str:
        return f"PatternAnalysisRun({self.symbol}, {self.as_of})"


__all__ = ["HistoricalFeatureVector", "PatternAnalysisRun"]
