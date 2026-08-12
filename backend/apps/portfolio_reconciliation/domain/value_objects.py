"""PORTFOLIO-RECONCILE-1 — domain value objects.

``EntityType`` and ``DriftClassification`` are the pure domain building
blocks of the reconciliation context. None of them touch Django models;
the drift taxonomy is shared verbatim between the application services
(which classify), the ``DriftRecord`` table (which persists the result)
and the ``portfolio_reconciliation.*`` events (which publish it).
"""

from __future__ import annotations

from enum import Enum


class EntityType(str, Enum):
    """The authoritative write-model side of a reconciliation pass."""

    POSITION = "POSITION"
    ORDER = "ORDER"

    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        return [(member.value, member.value) for member in cls]


class DriftClassification(str, Enum):
    """Every way a read-model row can diverge from its source of truth.

    Exactly one classification is produced per ``(account, key)`` during a
    reconciliation run:

    - ``MATCHED``: read model agrees with the write model (never persisted).
    - ``MISSING_IN_READ_MODEL``: open in the write model, absent (or closed)
      in the read model — auto-repairable by a fresh projection.
    - ``STALE_IN_READ_MODEL``: present in both but values differ —
      auto-repairable by overwriting from the write model.
    - ``ORPHANED_IN_READ_MODEL``: open in the read model with no matching
      write-model row — NEVER auto-repaired (closing would fabricate a
      position close nobody asked for); surfaced for manual review.
    - ``COMPARISON_ERROR``: a single row could not be compared/repaired
      (malformed snapshot, storage failure, or a read-model column that
      cannot represent the write-model value). Never aborts the run.
    """

    MATCHED = "MATCHED"
    MISSING_IN_READ_MODEL = "MISSING_IN_READ_MODEL"
    STALE_IN_READ_MODEL = "STALE_IN_READ_MODEL"
    ORPHANED_IN_READ_MODEL = "ORPHANED_IN_READ_MODEL"
    COMPARISON_ERROR = "COMPARISON_ERROR"

    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        return [(member.value, member.value) for member in cls]
