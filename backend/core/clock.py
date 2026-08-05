"""TradeVision AI — Simulation clock (M3 historical replay).

Production components read "now" through :func:`get_clock` instead of calling
``datetime.now`` directly. Under normal operation the clock returns real wall
time; a backtest run wraps its replay in :func:`bind_simulated_time` so every
downstream consumer (risk evaluation, market-hours checks, freshness checks,
fill timestamps) evaluates against the historical snapshot timestamp instead.

The simulated time is carried in a :mod:`contextvars` ContextVar, so it only
propagates within the current execution context. This is why backtests must
run with ``CELERY_TASK_ALWAYS_EAGER=True`` — real Celery worker processes do
not inherit the caller's context, and simulated time would silently stop
propagating.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """The minimal contract every clock adapter satisfies.

    A ``Clock`` answers "what time is it now" in UTC. Production uses
    :class:`SystemClock`; backtest replay uses :class:`SimulationClock`
    pinned to a historical snapshot timestamp.
    """

    def now(self) -> datetime:
        """Return the current instant as a timezone-aware UTC datetime."""
        ...


class SystemClock:
    """Wall-clock adapter used in production and any non-simulated context."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class SimulationClock:
    """Historical-event timestamp adapter used by backtest replay.

    ``now()`` always returns the pinned snapshot timestamp, making market
    open/closed state, freshness, and fill ``occurred_at`` reproducible.
    """

    def __init__(self, simulated_at: datetime) -> None:
        if simulated_at.tzinfo is None:
            simulated_at = simulated_at.replace(tzinfo=timezone.utc)
        self._simulated_at = simulated_at

    def now(self) -> datetime:
        return self._simulated_at

    def __repr__(self) -> str:
        return f"SimulationClock({self._simulated_at.isoformat()})"


_simulated_time: contextvars.ContextVar[datetime | None] = contextvars.ContextVar(
    "tradevision_simulated_time", default=None
)


def get_clock() -> Clock:
    """Return the active clock for the current execution context.

    Returns a :class:`SimulationClock` when a backtest bound a historical
    timestamp via :func:`bind_simulated_time`; otherwise a
    :class:`SystemClock` (real wall time). Production behavior is unchanged
    because nothing ever binds simulated time outside backtest replay.
    """
    simulated_at = _simulated_time.get()
    if simulated_at is not None:
        return SimulationClock(simulated_at)
    return SystemClock()


@contextmanager
def bind_simulated_time(simulated_at: datetime) -> None:
    """Bind a historical timestamp for the duration of the ``with`` block.

    Every ``get_clock().now()`` call inside the block (and any Celery eager
    tasks it triggers) returns ``simulated_at``. The previous value is
    restored on exit, so contexts nest safely.
    """
    token = _simulated_time.set(simulated_at)
    try:
        yield
    finally:
        _simulated_time.reset(token)
