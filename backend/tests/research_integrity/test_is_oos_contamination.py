"""In-sample / out-of-sample contamination integrity.

Attacks attempted:
- Partition the IS/OOS split on the WALL-CLOCK ``order.created_at`` instead of
  simulated bar time. Real replays run in the present (wall clock 2026) while
  bars are historical (2024), so EVERY trade lands in OOS and IS is always
  empty — a silent IS/OOS contamination (RESEARCH-INTEGRITY-1, PROVEN AND
  FIXED).
- A trade whose first fill lands exactly ON ``split_ts`` (boundary) and one a
  second after it (must go to OOS).
- A trade being double-counted or dropped by the partition (must be partitioned
  exactly once).

Findings:
- The split now uses the first fill's simulated ``occurred_at``
  (``first_fill_at`` map in ``run_stats``), so a real replay's IS/OOS halves
  are correct. Boundary is inclusive (``<= split_ts`` -> IS).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tests.research_integrity.conftest import make_run

pytestmark = pytest.mark.django_db


def _seed_trade(
    run,
    *,
    entry: str,
    fill: str,
    occurred_at: datetime,
    side: str = "LONG",
    qty: int = 100,
) -> None:
    """Zero-cost FILLED order + fill for ``run``'s account."""
    from apps.execution.infrastructure.models import ExecutionRequest, Fill, Order

    corr = uuid.uuid4()
    req = ExecutionRequest.objects.create(
        idempotency_key=f"ri-key-{corr}",
        account_id=run.account_id,
        symbol=run.symbol,
        side=side,
        quantity=Decimal(qty),
        entry_price=Decimal(entry),
        stop_loss=Decimal("90.00"),
        correlation_id=corr,
        risk_approved_event_id=uuid.uuid4(),
        rule_id="long_momentum_v1",
        event_type="BREAKOUT",
        status="FILLED",
    )
    order = Order.objects.create(
        execution_request=req,
        account_id=run.account_id,
        symbol=run.symbol,
        side=side,
        quantity=Decimal(qty),
        status="FILLED",
        filled_quantity=Decimal(qty),
        avg_fill_price=Decimal(fill),
        entry_price=Decimal(entry),
        stop_loss=Decimal("90.00"),
        correlation_id=corr,
    )
    # auto_now_add ignores explicit values on save(); set it afterwards.
    Order.objects.filter(id=order.id).update(created_at=occurred_at)
    Fill.objects.create(
        order=order,
        sequence=1,
        quantity=Decimal(qty),
        price=Decimal(fill),
        occurred_at=occurred_at,
    )


def _split_ts(run) -> datetime:
    total_seconds = (run.range_end - run.range_start).total_seconds()
    offset = timedelta(seconds=total_seconds * float(run.in_sample_ratio))
    return run.range_start + offset


def _stats(run):
    from apps.backtesting.services import BacktestStatsService

    return BacktestStatsService().run_stats(run)


def test_real_replay_partitions_by_simulated_fill_time(replay):
    """Regression for RESEARCH-INTEGRITY-1: a REAL replay's trades must be
    split by simulated bar time, not wall clock. Pre-fix: both land in OOS and
    IS is empty."""
    start = datetime(2024, 6, 9, 5, 0, 0, tzinfo=timezone.utc)
    end = datetime(2024, 6, 9, 13, 0, 0, tzinfo=timezone.utc)
    bars = [
        (start + timedelta(hours=2), "100.00", "103.00"),  # fills @09:00 -> IS
        (start + timedelta(hours=4), "104.00", "107.00"),  # fills @11:00 -> OOS
        (start + timedelta(hours=6), "108.00", "111.00"),  # rejected (exposure)
    ]
    run, _result, _bus = replay(
        seed_bars=bars,
        range_start=start,
        range_end=end,
        in_sample_ratio=Decimal("0.5"),  # split at 09:00 exactly
        commission_rate=Decimal(0),
        slippage_bps=Decimal(0),
    )

    from apps.execution.infrastructure.models import Order

    # Wall clock is far in the future of the simulated data (2026 vs 2024) —
    # exactly what used to send every trade to OOS.
    orders = list(Order.objects.filter(account_id=run.account_id))
    assert all(order.created_at.year >= 2026 for order in orders)
    assert run.range_start.year == 2024

    stats = _stats(run)
    assert stats["trade_count"] == 2
    assert stats["in_sample"]["trade_count"] == 1
    assert stats["out_of_sample"]["trade_count"] == 1
    # The IS half holds the bar-1 trade (entry 103) and OOS holds bar-2 (107).
    assert Decimal(stats["in_sample"]["trades"][0]["entry_price"]) == Decimal(103)
    assert Decimal(stats["out_of_sample"]["trades"][0]["entry_price"]) == Decimal(107)


def test_fill_exactly_on_split_is_in_sample_and_one_second_after_is_oos():
    """Boundary inclusivity: ``occurred_at == split_ts`` -> IS, one second
    later -> OOS."""
    run = make_run(in_sample_ratio=Decimal("0.5"))
    split = _split_ts(run)

    _seed_trade(run, entry="100.00", fill="101.00", occurred_at=split)
    _seed_trade(run, entry="100.00", fill="101.00", occurred_at=split + timedelta(seconds=1))

    stats = _stats(run)
    assert stats["trade_count"] == 2
    assert stats["in_sample"]["trade_count"] == 1
    assert stats["out_of_sample"]["trade_count"] == 1


def test_every_trade_partitioned_exactly_once():
    """No trade may be double-counted, dropped, or counted in both halves."""
    run = make_run(in_sample_ratio=Decimal("0.5"))
    split = _split_ts(run)
    before = split - timedelta(days=1)
    after = split + timedelta(days=1)

    for occurred_at in (before, split, after):
        _seed_trade(run, entry="100.00", fill="101.00", occurred_at=occurred_at)

    stats = _stats(run)
    assert stats["trade_count"] == 3
    assert stats["in_sample"]["trade_count"] == 2
    assert stats["out_of_sample"]["trade_count"] == 1

    is_ids = {t["order_id"] for t in stats["in_sample"]["trades"]}
    oos_ids = {t["order_id"] for t in stats["out_of_sample"]["trades"]}
    assert len(is_ids) + len(oos_ids) == 3
    assert is_ids.isdisjoint(oos_ids)