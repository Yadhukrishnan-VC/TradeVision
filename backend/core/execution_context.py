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
from decimal import Decimal
from uuid import UUID

_account_override: contextvars.ContextVar[UUID | None] = contextvars.ContextVar(
    "tradevision_execution_account_override", default=None
)
_commission_rate: contextvars.ContextVar[Decimal | None] = contextvars.ContextVar(
    "tradevision_execution_commission_rate", default=None
)
_slippage_bps: contextvars.ContextVar[Decimal | None] = contextvars.ContextVar(
    "tradevision_execution_slippage_bps", default=None
)
_defer_fills: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "tradevision_execution_defer_fills", default=False
)
_next_bar_open: contextvars.ContextVar[Decimal | None] = contextvars.ContextVar(
    "tradevision_execution_next_bar_open", default=None
)


def get_account_override() -> UUID | None:
    """Return the active account override, or ``None`` outside replay."""
    return _account_override.get()


def get_backtest_commission_rate() -> Decimal | None:
    return _commission_rate.get()


def get_backtest_slippage_bps() -> Decimal | None:
    return _slippage_bps.get()


def get_backtest_defer_fills() -> bool:
    return _defer_fills.get()


def get_next_bar_open() -> Decimal | None:
    return _next_bar_open.get()


@contextmanager
def bind_account_override(account_id: UUID) -> None:
    """Route the current execution context's order flow to ``account_id``."""
    token = _account_override.set(account_id)
    try:
        yield
    finally:
        _account_override.reset(token)


@contextmanager
def bind_backtest_execution(
    commission_rate: Decimal | None = None,
    slippage_bps: Decimal | None = None,
    defer_fills: bool = False,
    next_bar_open: Decimal | None = None,
):
    """Bind backtest execution context variables for realistic fill pricing."""
    token_comm = _commission_rate.set(commission_rate)
    token_slip = _slippage_bps.set(slippage_bps)
    token_defer = _defer_fills.set(defer_fills)
    token_open = _next_bar_open.set(next_bar_open)
    try:
        yield
    finally:
        _commission_rate.reset(token_comm)
        _slippage_bps.reset(token_slip)
        _defer_fills.reset(token_defer)
        _next_bar_open.reset(token_open)
