"""Backtest-run account routing context (M3).

Backtest replay runs the real event-driven pipeline, but orders must land on
the run's isolated account rather than the ``is_default`` account that
production intake resolves. The runner binds the backtest ``account_id`` for
the duration of each historical bar's ingestion; the rule_engine publisher
reads it once and threads it as an optional ``account_id`` payload field
through ``RuleFired`` -> ``RiskApproved`` -> ``ExecutionRequestService``.

Like the simulation clock, the account id lives in a ContextVar so it only
propagates within the current execution context (hence the
``CELERY_TASK_ALWAYS_EAGER`` requirement for backtests). When nothing is
bound, ``get_backtest_account_id()`` returns ``None`` and every producer
falls back to today's ``is_default`` behavior unchanged.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from uuid import UUID

_backtest_account_id: contextvars.ContextVar[UUID | None] = contextvars.ContextVar(
    "tradevision_backtest_account_id", default=None
)


def get_backtest_account_id() -> UUID | None:
    """Return the active backtest account id, or ``None`` outside replay."""
    return _backtest_account_id.get()


@contextmanager
def bind_backtest_account(account_id: UUID) -> None:
    """Route the current execution context's order flow to ``account_id``."""
    token = _backtest_account_id.set(account_id)
    try:
        yield
    finally:
        _backtest_account_id.reset(token)
