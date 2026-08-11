from datetime import datetime, timezone
from decimal import Decimal

import pytest

from apps.backtesting.models import BacktestRun
from apps.backtesting.services import BacktestRunnerService, BacktestStatsService
from apps.backtesting.tests.conftest import _make_ta_payload
from apps.execution.infrastructure.models import Fill, Order
from apps.portfolio.infrastructure.price_source import MarketDataCurrentPriceProvider
from apps.technical_analysis.infrastructure.models import TASnapshot


@pytest.fixture
def multi_bar_ta_snapshots(db):
    """Seed multi-bar TA snapshots for testing edge validation."""
    snapshots = []

    # Bar 1 (2024-06-01 09:15)
    s1 = TASnapshot.objects.create(
        symbol="RELIANCE",
        timeframe="15min",
        snapshot_timestamp=datetime(2024, 6, 1, 9, 15, tzinfo=timezone.utc),
        raw_payload={
            "symbol": "RELIANCE",
            "timeframe": "15min",
            "open": 100.0,
            "high": 103.0,
            "low": 99.9,
            "close": 102.5,
            "volume": 3500,
            "current_price": 102.5,
            "vwap": 101.0,
            "ema_20": 100.5,
            "avg_volume_10d": 1000,
            "opening_15m_open": 100.0,
            "opening_15m_high": 103.0,
            "opening_15m_low": 99.98,
            "opening_15m_close": 102.5,
        },
    )
    snapshots.append(s1)

    # Bar 2 (2024-06-01 09:30) - Next Bar Open is 103.00
    s2 = TASnapshot.objects.create(
        symbol="RELIANCE",
        timeframe="15min",
        snapshot_timestamp=datetime(2024, 6, 1, 9, 30, tzinfo=timezone.utc),
        raw_payload={
            "symbol": "RELIANCE",
            "timeframe": "15min",
            "open": 103.0,
            "high": 108.0,
            "low": 102.5,
            "close": 107.0,
            "volume": 2000,
            "current_price": 107.0,
            "vwap": 103.5,
            "ema_20": 102.0,
            "avg_volume_10d": 1000,
            "opening_15m_open": 100.0,
            "opening_15m_high": 103.0,
            "opening_15m_low": 99.98,
            "opening_15m_close": 102.5,
        },
    )
    snapshots.append(s2)

    return snapshots


@pytest.mark.django_db
def test_strategy_edge_validation_e2e(funded_account, multi_bar_ta_snapshots, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.EXECUTION_ENGINE_ENABLED = True

    run = BacktestRun.objects.create(
        symbol="RELIANCE",
        timeframe="15min",
        range_start=datetime(2024, 6, 1, 9, 0, tzinfo=timezone.utc),
        range_end=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
        account=funded_account,
        commission_rate=Decimal("0.0003"),
        slippage_bps=Decimal("5.0"),
        in_sample_ratio=Decimal("0.70"),
    )

    runner = BacktestRunnerService()
    res = runner.run(run.id)

    assert res["status"] == "COMPLETED"

    run.refresh_from_db()
    stats_service = BacktestStatsService()
    report = stats_service.run_stats(run)

    assert report["status"] == "COMPLETED"
    assert "total_transaction_costs" in report
    assert "expectancy" in report
    assert "profit_factor" in report
    assert "max_drawdown_pct" in report
    assert "benchmark_return_pct" in report
    assert "in_sample" in report
    assert "out_of_sample" in report

    run.refresh_from_db()
    assert run.net_pnl is not None
    assert run.expectancy is not None


@pytest.mark.django_db
def test_multi_bar_fills_defer_to_next_bar_open(
    seed_session_facts,
    register_all_handlers,
    active_bus,
    funded_account,
    settings,
    monkeypatch,
):
    """A bar-N signal must fill at bar-(N+1)'s real open, never at its own close.

    Proves the M3.8-FIX look-ahead guarantee end to end: the deferred order's
    fill price and timestamp come from the following bar, and the first bar's
    entry (103.00) is NOT used as the fill price.
    """
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.EXECUTION_ENGINE_ENABLED = True
    monkeypatch.setattr(
        MarketDataCurrentPriceProvider,
        "get_current_price",
        lambda self, symbol: None,
    )
    register_all_handlers(active_bus)

    t1 = datetime(2024, 6, 10, 5, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2024, 6, 10, 6, 0, 0, tzinfo=timezone.utc)
    for bar_ts, overrides in (
        (t1, {"open": "100.00", "close": "103.00"}),
        (t2, {"open": "110.00", "close": "108.00"}),
    ):
        TASnapshot.objects.create(
            symbol="RELIANCE",
            exchange="NSE",
            timeframe="1D",
            pine_id="long_momentum@tv",
            pine_version="5",
            indicators={"vwap": "101.50", "ema_20": "102.00"},
            raw_payload=_make_ta_payload(**overrides),
            snapshot_timestamp=bar_ts,
        )

    run = BacktestRun.objects.create(
        symbol="RELIANCE",
        timeframe="1D",
        range_start=datetime(2024, 6, 9, tzinfo=timezone.utc),
        range_end=datetime(2024, 6, 11, tzinfo=timezone.utc),
        account=funded_account,
        status="PENDING",
        commission_rate=Decimal("0.0003"),
        slippage_bps=Decimal("5.0"),
    )

    result = BacktestRunnerService().run(run.id)
    assert result["status"] == "COMPLETED"
    assert result["bars_processed"] == "2"

    orders = list(
        Order.objects.filter(account_id=funded_account.id).order_by("created_at")
    )
    assert len(orders) == 2
    assert orders[0].status == "FILLED"
    assert orders[0].entry_price == Decimal("103.00")

    first_fill = Fill.objects.get(order=orders[0])
    assert first_fill.quantity == orders[0].quantity
    # Bar-1 signal filled at bar-2 OPEN (110.00) + 5bps slippage = 110.055,
    # NOT at bar-1's close/entry (103.00) — chronological causality preserved.
    assert first_fill.price == Decimal("110.055")
    assert orders[0].avg_fill_price == first_fill.price
    assert first_fill.occurred_at == t2

    stats = BacktestStatsService().run_stats(run)
    assert stats["trade_count"] == 2
    assert stats["fill_count"] == 2
    assert stats["trades"][0]["entry_price"] == "103.00000000"
    assert stats["trades"][0]["avg_fill_price"] == "110.05500000"
