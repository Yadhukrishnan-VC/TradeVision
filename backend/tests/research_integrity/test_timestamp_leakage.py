"""Timestamp leakage integrity.

Attacks attempted:
- Fill/execution timestamps leak WALL-CLOCK time (``datetime.now()``) instead
  of the simulated bar time, so any time-based statistic (IS/OOS split,
  regime bucketing, walk-forward) silently mislabels trades (RESEARCH-INTEGRITY-1
  family).
- Duplicate/out-of-order bar timestamps cause a fill to be stamped with the
  wrong bar or the engine to skip bars.

Findings:
- Fills carry the simulated ``occurred_at`` of the bar whose OPEN executed
  them — always within the declared backtest range, never wall clock
  (no-defect finding, verified below).
- Bars with identical timestamps are all processed independently and do not
  collide (there is no unique constraint on ``snapshot_timestamp``; the engine
  iterates in timestamp order).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db


def test_fill_timestamps_are_simulated_not_wall_clock(replay):
    """Every fill's ``occurred_at`` must be inside the backtest range and long
    before wall-clock now (the run executes in the present, bars are 2024)."""
    from datetime import datetime as _dt

    d1 = datetime(2024, 6, 9, 7, 0, 0, tzinfo=timezone.utc)
    bars = [
        (d1, "100.00", "103.00"),
        (d1 + timedelta(hours=2), "104.00", "107.00"),
        (d1 + timedelta(hours=4), "108.00", "111.00"),  # rejected (exposure)
    ]
    run, _result, _bus = replay(
        seed_bars=bars,
        commission_rate=Decimal(0),
        slippage_bps=Decimal(0),
    )

    from apps.execution.infrastructure.models import Fill

    fills = list(Fill.objects.filter(order__account_id=run.account_id))
    assert len(fills) == 2
    now = _dt.now(timezone.utc)
    for fill in fills:
        assert run.range_start <= fill.occurred_at <= run.range_end
        assert fill.occurred_at < now  # never wall clock
        assert fill.occurred_at.year == 2024


def test_duplicate_bar_timestamps_do_not_collide(replay):
    """Two bars with the SAME timestamp are both processed and both generate
    their own fills (no unique-constraint clash, no silent skip)."""
    d1 = datetime(2024, 6, 9, 7, 0, 0, tzinfo=timezone.utc)
    bars = [
        (d1, "100.00", "103.00"),
        (d1, "104.00", "107.00"),  # identical timestamp
    ]
    run, result, _bus = replay(
        seed_bars=bars,
        commission_rate=Decimal(0),
        slippage_bps=Decimal(0),
    )

    from apps.execution.infrastructure.models import Fill, Order

    assert result["status"] == "COMPLETED"
    assert result["bars_processed"] == "2"
    orders = list(Order.objects.filter(account_id=run.account_id))
    fills = list(Fill.objects.filter(order__account_id=run.account_id))
    assert len(orders) == 2
    assert len(fills) == 2


def test_fill_never_predates_the_executing_bar(replay):
    """A fill's simulated time must equal the bar whose OPEN filled it."""
    d1 = datetime(2024, 6, 9, 7, 0, 0, tzinfo=timezone.utc)
    bars = [
        (d1, "100.00", "103.00"),
        (d1 + timedelta(hours=2), "104.00", "107.00"),
    ]
    run, _result, _bus = replay(
        seed_bars=bars,
        commission_rate=Decimal(0),
        slippage_bps=Decimal(0),
    )

    from apps.execution.infrastructure.models import Fill

    fills = sorted(Fill.objects.filter(order__account_id=run.account_id), key=lambda f: f.occurred_at)
    assert fills[0].occurred_at == d1 + timedelta(hours=2)  # bar 2 open executed it
    assert fills[1].occurred_at == d1 + timedelta(hours=2)  # final-bar flush same ts