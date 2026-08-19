"""Look-ahead bias integrity.

Attacks attempted:
- A bar arrives with NO ``open`` field and the runner falls back to the bar's
  CLOSE to fill a deferred order — the fill uses a price not yet known at the
  moment the market would have opened (RESEARCH-INTEGRITY-2, PROVEN AND FIXED).
- The runner fills a deferred order on the very bar whose indicator values it
  is reading, i.e. it executes on the same candle it just "saw" close.

Findings:
- Before the fix, ``bar_open = raw.get("open") or raw.get("close")`` silently
  substituted the close. The regression test below fails on the old code and
  passes on the fixed code (which requires an ``open`` and otherwise skips the
  fill, leaving the order pending until a bar with an ``open`` arrives).
- Fail-safe behaviour is asserted directly: a bar without an ``open`` neither
  fills nor crashes; the order survives to the next bar with an ``open``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db


def test_missing_open_skips_fill_never_falls_back_to_close(replay):
    """Regression for RESEARCH-INTEGRITY-2: no-open bar must NOT fill at its
    close. The deferred order instead fills at the next bar that HAS an open."""
    d1 = datetime(2024, 6, 9, 7, 0, 0, tzinfo=timezone.utc)
    bars = [
        (d1, "100.00", "103.00"),  # signal -> deferred
        (d1 + timedelta(hours=2), None, "107.00"),  # NO open: must skip, not fill at 107
        (d1 + timedelta(hours=4), "112.00", "115.00"),  # open present -> fill here
    ]
    run, _result, _bus = replay(
        seed_bars=bars,
        commission_rate=Decimal(0),
        slippage_bps=Decimal(0),
    )

    from apps.execution.infrastructure.models import Order

    orders = list(
        Order.objects.filter(account_id=run.account_id).order_by("entry_price")
    )
    assert len(orders) == 2
    first = orders[0]
    assert Decimal(first.entry_price) == Decimal("103.00")  # bar 1 signal
    assert Decimal(first.avg_fill_price) == Decimal("112.00")  # bar 3 open
    assert Decimal(first.avg_fill_price) != Decimal("107.00")  # NOT bar 2 close


def test_no_open_bar_is_fail_safe_never_crashes(replay):
    """A middle bar missing its ``open`` is skipped defensively: the run stays
    COMPLETED and every surviving order fills at a LATER bar's open — never at
    the no-open bar's close."""
    d1 = datetime(2024, 6, 9, 7, 0, 0, tzinfo=timezone.utc)
    bars = [
        (d1, "100.00", "103.00"),
        (d1 + timedelta(hours=2), None, "107.00"),  # NO open: must be skipped
        (d1 + timedelta(hours=4), "112.00", "115.00"),
    ]
    run, result, _bus = replay(
        seed_bars=bars,
        commission_rate=Decimal(0),
        slippage_bps=Decimal(0),
    )

    assert result["status"] == "COMPLETED"
    from apps.execution.infrastructure.models import Order

    orders = list(Order.objects.filter(account_id=run.account_id).order_by("entry_price"))
    assert len(orders) == 2  # bar-1 + bar-2 signals; bar-3 rejected (exposure)
    for order in orders:
        assert order.status == "FILLED"
        assert Decimal(order.avg_fill_price) == Decimal("112.00")  # bar 3 open
        assert Decimal(order.avg_fill_price) != Decimal("107.00")  # NOT bar 2 close