"""M3 simulation clock unit tests.

The clock is the mechanism that makes historical replay reproducible: risk
evaluation, market-hours checks, freshness checks and fill timestamps all
read ``get_clock().now()`` instead of the wall clock.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.clock import (
    SimulationClock,
    SystemClock,
    bind_simulated_time,
    get_clock,
)

pytestmark = pytest.mark.django_db


def test_system_clock_returns_utc_aware_now() -> None:
    before = datetime.now(timezone.utc)
    now = SystemClock().now()
    after = datetime.now(timezone.utc)
    assert now.tzinfo is not None
    assert now.utcoffset().total_seconds() == 0
    assert before <= now <= after


def test_simulation_clock_pins_timestamp() -> None:
    pinned = datetime(2024, 6, 10, 7, 0, 0, tzinfo=timezone.utc)
    clock = SimulationClock(pinned)
    assert clock.now() == pinned
    assert clock.now() == pinned


def test_simulation_clock_treats_naive_input_as_utc() -> None:
    naive = datetime(2024, 6, 10, 7, 0, 0)
    clock = SimulationClock(naive)
    assert clock.now().tzinfo is not None
    assert clock.now() == naive.replace(tzinfo=timezone.utc)


def test_get_clock_defaults_to_system_outside_replay() -> None:
    clock = get_clock()
    assert isinstance(clock, SystemClock)
    assert (datetime.now(timezone.utc) - clock.now()).total_seconds() < 5


def test_bind_simulated_time_propagates_inside_block() -> None:
    pinned = datetime(2024, 6, 10, 7, 0, 0, tzinfo=timezone.utc)
    with bind_simulated_time(pinned):
        clock = get_clock()
        assert isinstance(clock, SimulationClock)
        assert clock.now() == pinned
        assert get_clock().now() == pinned


def test_bind_simulated_time_restores_after_block() -> None:
    pinned = datetime(2024, 6, 10, 7, 0, 0, tzinfo=timezone.utc)
    with bind_simulated_time(pinned):
        assert get_clock().now() == pinned
    assert isinstance(get_clock(), SystemClock)
    assert (datetime.now(timezone.utc) - get_clock().now()).total_seconds() < 5


def test_bind_simulated_time_nests_safely() -> None:
    outer = datetime(2024, 6, 10, 7, 0, 0, tzinfo=timezone.utc)
    inner = outer + timedelta(minutes=30)
    with bind_simulated_time(outer):
        with bind_simulated_time(inner):
            assert get_clock().now() == inner
        assert get_clock().now() == outer
    assert isinstance(get_clock(), SystemClock)


def test_bind_simulated_time_restores_on_exception() -> None:
    pinned = datetime(2024, 6, 10, 7, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(RuntimeError):
        with bind_simulated_time(pinned):
            assert get_clock().now() == pinned
            raise RuntimeError("boom")
    assert isinstance(get_clock(), SystemClock)
