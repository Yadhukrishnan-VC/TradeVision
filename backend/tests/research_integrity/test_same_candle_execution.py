"""Same-candle execution integrity.

Attacks attempted:
- Signal bar and fill bar are the same bar (the strategy "sees" the bar's
  close, then fills on that same close — a look-ahead price).
- Fill happens at the signal bar's close instead of the next bar's open.

Findings:
- The runner defers every generated order to the next bar's OPEN; no order is
  filled on the bar that generated it (RESEARCH-INTEGRITY-2, a no-defect
  finding — verified below).
- The FINAL bar of a replay is a documented boundary: an order generated on the
  last bar is flushed at that same bar's close. This is pinned here as a known
  end-of-sample convention (RESEARCH-INTEGRITY-REMAINING-1) rather than
  silently changing behaviour.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tests.research_integrity.conftest import BASE

pytestmark = pytest.mark.django_db


def _orders_and_fills(run_id):
    from apps.execution.infrastructure.models import Fill, Order

    orders = list(
        Order.objects.filter(account_id=run_id.account_id)
        .order_by("entry_price")
        .values_list("id", "entry_price", "avg_fill_price", "status")
    )
    fills = {
        str(order_id): occurred_at
        for order_id, occurred_at in Fill.objects.filter(
            order__account_id=run_id.account_id
        ).values_list("order_id", "occurred_at")
    }
    return orders, fills


def test_fill_occurs_at_next_bar_open_never_signal_bar_close(replay):
    """An order generated on bar N is filled at bar N+1's open price."""
    d1 = datetime(2024, 6, 9, 7, 0, 0, tzinfo=timezone.utc)
    bars = [
        (d1, "100.00", "103.00"),  # signal -> deferred to 09:00 open
        (d1 + timedelta(hours=2), "104.00", "107.00"),  # signal -> deferred to 11:00 open
        (d1 + timedelta(hours=4), "108.00", "111.00"),  # signal -> rejected (exposure)
    ]
    run, _result, _bus = replay(
        seed_bars=bars,
        commission_rate=Decimal(0),
        slippage_bps=Decimal(0),
    )

    orders, _fills = _orders_and_fills(run)
    assert len(orders) == 2
    first_entry, first_fill = Decimal(orders[0][1]), Decimal(orders[0][2])
    second_entry, second_fill = Decimal(orders[1][1]), Decimal(orders[1][2])

    assert first_entry == Decimal("103.00")  # bar 1 close, known at signal time
    assert first_fill == Decimal("104.00")  # bar 2 open, never bar 1 close
    assert second_entry == Decimal("107.00")  # bar 2 close
    assert second_fill == Decimal("108.00")  # bar 3 open, never bar 2 close
    assert all(status == "FILLED" for *_entry, status in orders)


def test_fill_timestamp_is_next_bar_not_signal_bar(replay):
    """The fill's simulated timestamp is the next bar's, not the signal bar's."""
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

    _, fills = _orders_and_fills(run)
    assert len(fills) == 2
    assert sorted(fills.values()) == [
        d1 + timedelta(hours=2),  # order from bar 1 filled at bar 2 open
        d1 + timedelta(hours=4),  # order from bar 2 filled at bar 3 open
    ]


def test_final_bar_flush_is_documented_end_of_sample_convention(replay):
    """Pins the final-bar boundary: an order from the LAST bar fills at that
    bar's close. End-of-sample liquidation; flagged in the report as
    RESEARCH-INTEGRITY-REMAINING-1."""
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

    orders, _fills = _orders_and_fills(run)
    second = Decimal(orders[1][2])
    assert second == Decimal("107.00")  # last bar's own close
    assert BASE is not None  # keep module import purposeful