"""TradeVision AI — Execution account override context (M3 historical replay).

Backtest replay runs the real event-driven pipeline, but orders must land on
the run's isolated account rather than the ``is_default`` account that
production intake resolves. The runner binds the backtest ``account_id`` for
the duration of each historical bar's ingestion; the rule_engine publisher
reads it once and threads it as an optional ``account_id`` payload field
through ``RuleFired`` -> ``RiskApproved`` -> ``ExecutionRequestService``.

Like the simulation clock, the account id lives in a ContextVar so it only
propagates within the current execution context (hence the
``CELERY_TASK_ALWAYS_EAGER`` requirement for backtests). When nothing is
bound, ``get_account_override()`` returns ``None`` and every producer falls
back to today's ``is_default`` behavior unchanged.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from uuid import UUID

_account_override: contextvars.ContextVar[UUID | None] = contextvars.ContextVar(
    "tradevision_execution_account_override", default=None
)


def get_account_override() -> UUID | None:
    """Return the active account override, or ``None`` outside replay."""
    return _account_override.get()


@contextmanager
def bind_account_override(account_id: UUID) -> None:
    """Route the current execution context's order flow to ``account_id``."""
    token = _account_override.set(account_id)
    try:
        yield
    finally:
        _account_override.reset(token)
