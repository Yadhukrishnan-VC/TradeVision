"""PORTFOLIO-RECONCILE-1 — domain exceptions.

Defensive boundary: a single drifted row must never take down a whole
reconciliation run. The repositories raise :class:`DriftPersistenceError`
when a repair write fails at the storage layer; the application services
catch it (alongside any malformed-row error) and classify the row as
``COMPARISON_ERROR`` instead of propagating.
"""

from __future__ import annotations


class ReconciliationError(Exception):
    """Base class for portfolio-reconciliation domain errors."""


class DriftPersistenceError(ReconciliationError):
    """Raised when persisting a repair or a drift record fails.

    The application service treats this as a row-level failure: the
    offending key is logged and classified ``COMPARISON_ERROR``; the rest
    of the run continues untouched.
    """
