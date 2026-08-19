"""Walk-forward contamination integrity.

Attacks attempted:
- One walk-forward window's trades bleed into the NEXT window's run_stats
  (the classic walk-forward leakage: overlapping data shared across windows).
- A contaminating order seeded into window 0's account shows up in window 1's
  out-of-sample metrics.

Findings:
- ``WalkForwardService`` creates a dedicated funded ``Account`` per window and
  ``run_stats`` scopes strictly by ``account_id`` (no cross-account queries), so
  a window can never see another window's records (RESEARCH-INTEGRITY-4, a
  no-defect finding verified below).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from apps.backtesting.application.walk_forward_service import WalkForwardService

pytestmark = pytest.mark.django_db

_W0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
_WINDOW_SIZE = timedelta(days=60)
_STEP = timedelta(days=30)
_RANGE_END = _W0 + timedelta(days=150)


def _contaminating_trade(run) -> None:
    """One FILLED trade seeded straight into ``run``'s account."""
    from apps.execution.infrastructure.models import ExecutionRequest, Fill, Order

    corr = uuid.uuid4()
    req = ExecutionRequest.objects.create(
        idempotency_key=f"ri-wf-key-{corr}",
        account_id=run.account_id,
        symbol=run.symbol,
        side="LONG",
        quantity=Decimal(100),
        entry_price=Decimal("100.00"),
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
        side="LONG",
        quantity=Decimal(100),
        status="FILLED",
        filled_quantity=Decimal(100),
        avg_fill_price=Decimal("110.00"),
        entry_price=Decimal("100.00"),
        stop_loss=Decimal("90.00"),
        correlation_id=corr,
    )
    Order.objects.filter(id=order.id).update(created_at=_W0 + timedelta(days=5))
    Fill.objects.create(
        order=order,
        sequence=1,
        quantity=Decimal(100),
        price=Decimal("110.00"),
        occurred_at=_W0 + timedelta(days=5),
    )


class _ContaminationRunner:
    """Stub runner that injects a contaminating trade ONLY into window 0."""

    def __init__(self) -> None:
        self.calls: list[tuple[uuid.UUID, datetime]] = []

    def run(self, run_id: uuid.UUID) -> dict[str, str]:
        from apps.backtesting.models import BacktestRun

        run = BacktestRun.objects.get(id=run_id)
        self.calls.append((run_id, run.range_start))
        if run.range_start == _W0:
            _contaminating_trade(run)
        return {"status": "COMPLETED", "run_id": str(run_id), "bars_processed": "0"}


def test_window_zero_contamination_never_reaches_later_windows(django_user_model):
    """Window 1 must NOT see window 0's injected trade in either half."""
    user = django_user_model.objects.create_user(
        username=f"ri_wf_{uuid.uuid4().hex[:8]}", password="p"
    )
    runner = _ContaminationRunner()
    result = WalkForwardService(runner=runner).execute(
        owner=user,
        symbol="RELIANCE",
        timeframe="1D",
        range_start=_W0,
        range_end=_RANGE_END,
        window_size_days=60,
        step_size_days=30,
        in_sample_ratio=Decimal("0.50"),
    )

    windows = result["windows"]
    assert len(windows) == 4
    # Window 0 owns the injected trade (in-sample, before its 01-31 split).
    assert windows[0]["in_sample_trade_count"] == 1
    assert windows[0]["out_of_sample_trade_count"] == 0
    # Every later window is completely clean.
    for window in windows[1:]:
        assert window["in_sample_trade_count"] == 0
        assert window["out_of_sample_trade_count"] == 0
    assert len({w["account_id"] for w in windows}) == 4


def test_run_stats_is_strictly_account_scoped():
    """Direct invariant: a trade in account A never appears in run B's stats."""
    from apps.backtesting.services import BacktestStatsService
    from tests.research_integrity.conftest import make_run

    run_a = make_run()
    run_b = make_run()
    assert run_a.account_id != run_b.account_id

    _contaminating_trade(run_a)

    stats_b = BacktestStatsService().run_stats(run_b)
    assert stats_b["trade_count"] == 0
    assert stats_b["in_sample"]["trade_count"] == 0
    assert stats_b["out_of_sample"]["trade_count"] == 0

    stats_a = BacktestStatsService().run_stats(run_a)
    assert stats_a["trade_count"] == 1