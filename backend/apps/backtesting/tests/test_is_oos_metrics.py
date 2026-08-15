"""Batch IS-OOS-METRICS-1 — independent in-sample vs out-of-sample metrics.

``BacktestStatsService.run_stats()`` already splits trades into the static
in-sample / out-of-sample halves of the run's date range via
``run.in_sample_ratio`` (two sub-dicts with ``trade_count`` + ``trades``).
This batch adds the full metrics suite (expectancy, profit factor, max
drawdown, Sharpe, Sortino, win/loss counts, win rate, net P&L, gross
profit/loss) to each half, reusing the same per-bucket equity-curve/returns
accumulation and ``calculate_*`` helpers the by_regime/by_rule passes use.

These tests pin exact, hand-computed Decimal values for both halves of a
synthetic 6-trade fixture, prove every top-level aggregate key is unchanged
by the new pass, and assert the empty-out-of-sample edge case yields None
for the ratio-based metrics.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from apps.backtesting.domain.metrics import (
    calculate_max_drawdown,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
)
from apps.backtesting.services import BacktestStatsService

# in_sample_ratio=0.50 -> split_ts = 2024-06-10 00:00 UTC (range midpoint).
_BASE = datetime(2024, 6, 9, tzinfo=timezone.utc)


@pytest.mark.django_db
class TestIsOosMetrics:
    """Exact-value tests for the in-sample/out-of-sample stats pass."""

    def _create_trade(
        self,
        run,
        side: str,
        entry: str,
        fill: str,
        qty: int,
        created_at: datetime,
    ) -> None:
        from apps.execution.infrastructure.models import ExecutionRequest, Fill, Order

        corr = uuid.uuid4()
        account_id = run.account_id
        req = ExecutionRequest.objects.create(
            idempotency_key=f"key-{corr}",
            account_id=account_id,
            symbol="RELIANCE",
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
            account_id=account_id,
            symbol="RELIANCE",
            side=side,
            quantity=Decimal(qty),
            status="FILLED",
            filled_quantity=Decimal(qty),
            avg_fill_price=Decimal(fill),
            entry_price=Decimal(entry),
            stop_loss=Decimal("90.00"),
            correlation_id=corr,
        )
        # auto_now_add ignores explicit values on save(); set it afterwards so
        # the IS/OOS partition is deterministic.
        Order.objects.filter(id=order.id).update(created_at=created_at)
        Fill.objects.create(
            order=order,
            sequence=1,
            quantity=Decimal(qty),
            price=Decimal(fill),
            occurred_at=created_at,
        )

    def _seed_six_trades(self, run) -> None:
        """Zero-cost run, in_sample_ratio=0.50, 4 IS + 2 OOS trades.

        In-sample (created_at <= 2024-06-10 00:00 UTC): +1000, -500, +1500,
        +500. Out-of-sample: +200, -400.
        """
        run.commission_rate = Decimal("0")
        run.slippage_bps = Decimal("0")
        run.in_sample_ratio = Decimal("0.50")
        run.save()
        self._create_trade(run, "LONG", "100.00", "110.00", 100, _BASE.replace(hour=10))
        self._create_trade(run, "SHORT", "200.00", "205.00", 100, _BASE.replace(hour=11))
        self._create_trade(run, "LONG", "100.00", "115.00", 100, _BASE.replace(hour=12))
        self._create_trade(run, "LONG", "50.00", "55.00", 100, _BASE.replace(hour=13))
        self._create_trade(run, "LONG", "100.00", "102.00", 100, _BASE.replace(day=10, hour=10))
        self._create_trade(run, "SHORT", "200.00", "204.00", 100, _BASE.replace(day=10, hour=11))

    def test_in_sample_out_of_sample_metrics_hand_computed(self, backtest_run) -> None:
        self._seed_six_trades(backtest_run)

        stats = BacktestStatsService().run_stats(backtest_run)
        e = Decimal(stats["equity_at_completion"])
        assert e == Decimal("1000000")

        # -- In-sample: +1000, -500, +1500, +500 (3 wins / 1 loss).
        ins = stats["in_sample"]
        assert ins["trade_count"] == 4
        assert ins["win_count"] == 3
        assert ins["loss_count"] == 1
        assert Decimal(ins["gross_profit"]) == Decimal("3000")
        assert Decimal(ins["gross_loss"]) == Decimal("500")
        assert Decimal(ins["net_pnl"]) == Decimal("2500")
        assert Decimal(ins["win_rate"]) == Decimal("0.75")
        assert Decimal(ins["avg_win"]) == Decimal("1000")
        assert Decimal(ins["avg_loss"]) == Decimal("500")
        # E = 0.75 * 1000 - 0.25 * 500 = 625.
        assert Decimal(ins["expectancy"]) == Decimal("625")
        # PF = 3000 / 500 = 6.
        assert Decimal(ins["profit_factor"]) == Decimal("6")

        is_curve = [e, e + 1000, e + 500, e + 1500, e + 2000]
        is_dd_pct, is_dd_amt = calculate_max_drawdown(is_curve)
        assert Decimal(ins["max_drawdown_pct"]) == is_dd_pct
        assert Decimal(ins["max_drawdown_amount"]) == is_dd_amt
        is_returns = [
            Decimal("1000") / e,
            Decimal("-500") / (e + Decimal("1000")),
            Decimal("1500") / (e + Decimal("500")),
            Decimal("500") / (e + Decimal("2000")),
        ]
        assert Decimal(ins["sharpe_ratio"]) == calculate_sharpe_ratio(is_returns)
        assert Decimal(ins["sortino_ratio"]) == calculate_sortino_ratio(is_returns)
        assert [t["net_pnl"] for t in ins["trades"]] == [
            "1000.0000000000000000",
            "-500.0000000000000000",
            "1500.0000000000000000",
            "500.0000000000000000",
        ]

        # -- Out-of-sample: +200, -400 (1 win / 1 loss).
        oos = stats["out_of_sample"]
        assert oos["trade_count"] == 2
        assert oos["win_count"] == 1
        assert oos["loss_count"] == 1
        assert Decimal(oos["gross_profit"]) == Decimal("200")
        assert Decimal(oos["gross_loss"]) == Decimal("400")
        assert Decimal(oos["net_pnl"]) == Decimal("-200")
        assert Decimal(oos["win_rate"]) == Decimal("0.5")
        assert Decimal(oos["avg_win"]) == Decimal("200")
        assert Decimal(oos["avg_loss"]) == Decimal("400")
        # E = 0.5 * 200 - 0.5 * 400 = -100.
        assert Decimal(oos["expectancy"]) == Decimal("-100")
        # PF = 200 / 400 = 0.5.
        assert Decimal(oos["profit_factor"]) == Decimal("0.5")

        oos_curve = [e, e + 200, e - 200]
        oos_dd_pct, oos_dd_amt = calculate_max_drawdown(oos_curve)
        assert Decimal(oos["max_drawdown_pct"]) == oos_dd_pct
        assert Decimal(oos["max_drawdown_amount"]) == oos_dd_amt
        oos_returns = [
            Decimal("200") / e,
            Decimal("-400") / (e + Decimal("200")),
        ]
        assert Decimal(oos["sharpe_ratio"]) == calculate_sharpe_ratio(oos_returns)
        assert Decimal(oos["sortino_ratio"]) == calculate_sortino_ratio(oos_returns)
        assert [t["net_pnl"] for t in oos["trades"]] == [
            "200.0000000000000000",
            "-400.0000000000000000",
        ]

    def test_top_level_aggregates_unchanged_by_split_pass(self, backtest_run) -> None:
        """Byte-for-byte regression guard: the unconditioned aggregate must be
        identical to the pre-IS/OOS-metrics values for the same fixture."""
        self._seed_six_trades(backtest_run)

        stats = BacktestStatsService().run_stats(backtest_run)

        assert stats["trade_count"] == 6
        assert stats["fill_count"] == 6
        assert stats["win_count"] == 4
        assert stats["loss_count"] == 2
        assert stats["gross_profit"] == "3200.0000000000000000"
        assert stats["gross_loss"] == "900.0000000000000000"
        assert stats["total_transaction_costs"] == "0E-16"
        assert stats["total_slippage_impact"] == "0E-16"
        assert stats["net_pnl"] == "2300.0000000000000000"
        assert stats["win_rate"] == "0.6667"
        assert stats["expectancy"] == "383.3333333333333333333333334"
        assert stats["profit_factor"] == "3.555555555555555555555555556"
        assert stats["max_drawdown_pct"] == "0.04995004995004995004995004995"
        assert stats["sharpe_ratio"] == "7.7712"
        assert stats["sortino_ratio"] == "21.2797"
        assert stats["benchmark_return_pct"] is None
        assert stats["equity_at_completion"] == "1000000.00000000"
        assert stats["available_capital"] == "1000000.00000000"
        # IS + OOS trade counts still partition every trade.
        assert stats["in_sample"]["trade_count"] + stats["out_of_sample"]["trade_count"] == 6

    def test_empty_out_of_sample_ratio_metrics_are_none(self, backtest_run) -> None:
        """in_sample_ratio=1.0 puts every trade in-sample; the empty OOS half
        must yield None for ratio-based metrics (profit_factor, sharpe_ratio,
        sortino_ratio), mirroring the by_regime/by_rule too-few-trades
        convention, with exact zero/None values throughout."""
        self._seed_six_trades(backtest_run)
        backtest_run.in_sample_ratio = Decimal("1.00")
        backtest_run.save()

        stats = BacktestStatsService().run_stats(backtest_run)

        assert stats["in_sample"]["trade_count"] == 6
        assert stats["out_of_sample"]["trade_count"] == 0

        oos = stats["out_of_sample"]
        assert oos["trade_count"] == 0
        assert oos["win_count"] == 0
        assert oos["loss_count"] == 0
        assert Decimal(oos["gross_profit"]) == Decimal("0")
        assert Decimal(oos["gross_loss"]) == Decimal("0")
        assert Decimal(oos["total_transaction_costs"]) == Decimal("0")
        assert Decimal(oos["net_pnl"]) == Decimal("0")
        assert Decimal(oos["win_rate"]) == Decimal("0")
        assert Decimal(oos["avg_win"]) == Decimal("0")
        assert Decimal(oos["avg_loss"]) == Decimal("0")
        assert Decimal(oos["expectancy"]) == Decimal("0")
        assert oos["profit_factor"] is None
        assert oos["sharpe_ratio"] is None
        assert oos["sortino_ratio"] is None
        assert Decimal(oos["max_drawdown_pct"]) == Decimal("0")
        assert Decimal(oos["max_drawdown_amount"]) == Decimal("0")
        assert oos["trades"] == []

        # Cross-check: with all six trades in-sample, the IS half's metrics must
        # equal the unconditioned aggregate exactly.
        ins = stats["in_sample"]
        assert ins["trade_count"] == stats["trade_count"]
        assert Decimal(ins["net_pnl"]) == Decimal(stats["net_pnl"])
        assert Decimal(ins["win_rate"]) == Decimal(stats["win_rate"])
        assert Decimal(ins["expectancy"]) == Decimal(stats["expectancy"])
        assert Decimal(ins["profit_factor"]) == Decimal(stats["profit_factor"])
        assert Decimal(ins["max_drawdown_pct"]) == Decimal(stats["max_drawdown_pct"])
        assert Decimal(ins["sharpe_ratio"]) == Decimal(stats["sharpe_ratio"])
        assert Decimal(ins["sortino_ratio"]) == Decimal(stats["sortino_ratio"])
