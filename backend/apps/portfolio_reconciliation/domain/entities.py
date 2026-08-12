"""PORTFOLIO-RECONCILE-1 — domain entities.

``DriftRecord`` is the pure, persistence-agnostic entity a reconciliation
run hands to the infrastructure layer; ``ReconciliationResult`` is the
aggregate the application service returns to its caller (the Celery task).
Neither imports Django models.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from apps.portfolio_reconciliation.domain.value_objects import (
    DriftClassification,
)


def to_json_safe(value: object) -> object:
    """Render a domain value into a JSON-serialisable form.

    ``Decimal`` and ``datetime`` are the only non-JSON types carried in
    snapshot dicts; both are rendered as strings (matching the
    ``portfolio_reconciliation`` event payload convention).
    """
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def snapshot_from(mapping: dict[str, object]) -> dict[str, object]:
    """Render a ``{field: value}`` mapping into a JSON-safe snapshot dict."""
    return {key: to_json_safe(value) for key, value in mapping.items()}


@dataclass(frozen=True)
class DriftRecord:
    """One detected divergence between the read model and its source.

    Attributes:
        account_id: The account the drifted entity belongs to.
        entity_type: ``POSITION`` or ``ORDER`` (see :class:`EntityType`).
        entity_key: ``"<account_id>:<symbol>"`` for positions, the raw
            ``order_id`` for orders.
        classification: The :class:`DriftClassification` produced for the
            key.
        expected_snapshot: JSON-safe source-of-truth values at detection
            time (Decimals already rendered as strings).
        actual_snapshot: JSON-safe read-model values at detection time
            (``{}`` when the row was missing entirely).
        auto_repaired: Whether this drift was repaired in place by the run.
        detected_at: When the drift was observed (UTC).
        repaired_at: When the repair was applied (UTC); ``None`` when the
            drift was not auto-repaired.
    """

    account_id: uuid.UUID
    entity_type: str
    entity_key: str
    classification: DriftClassification
    expected_snapshot: dict[str, Any]
    actual_snapshot: dict[str, Any]
    auto_repaired: bool
    detected_at: datetime
    repaired_at: datetime | None = None


@dataclass
class ReconciliationResult:
    """Outcome of one ``*ReconciliationService.reconcile(account_id)`` run.

    ``matched`` counts the read-model rows that agreed with the write model
    (never persisted — the count exists only so operators can see how much
    of the book was verified clean). Every other count maps one-to-one to a
    persisted ``DriftRecord``.
    """

    account_id: uuid.UUID
    entity_type: str
    matched: int = 0
    missing_in_read_model: int = 0
    stale_in_read_model: int = 0
    orphaned_in_read_model: int = 0
    comparison_errors: int = 0
    auto_repaired: int = 0
    drift_records: list[DriftRecord] = field(default_factory=list)

    @property
    def total_drift(self) -> int:
        """Number of persisted drift records produced by this run."""
        return len(self.drift_records)

    def as_dict(self) -> dict[str, object]:
        """Plain mapping for task results / structured logs."""
        return {
            "account_id": str(self.account_id),
            "entity_type": self.entity_type,
            "matched": self.matched,
            "missing_in_read_model": self.missing_in_read_model,
            "stale_in_read_model": self.stale_in_read_model,
            "orphaned_in_read_model": self.orphaned_in_read_model,
            "comparison_errors": self.comparison_errors,
            "auto_repaired": self.auto_repaired,
            "total_drift": self.total_drift,
        }
