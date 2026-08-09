from datetime import datetime, timezone
from decimal import Decimal

import pytest

from apps.backtesting.models import BacktestRun
from apps.backtesting.services import BacktestRunnerService, BacktestStatsService
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
