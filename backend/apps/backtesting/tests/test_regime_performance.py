"""Batch REGIME-PERFORMANCE-1 — regime-conditional backtest performance analytics.

The regime that was live when a trade's originating signal fired is persisted
in ``RuleExecution.trigger_data["regime"]`` (same mechanism as the existing
``entry_price`` key). ``BacktestStatsService.run_stats()`` joins each ``Order``
back to that ``RuleExecution`` via ``correlation_id`` and recomputes the
existing metrics suite per regime bucket, in parallel with — never instead of
— the unconditioned aggregate.

These tests pin down exact, hand-computed Decimal values on a synthetic
multi-regime fixture, prove the unconditioned aggregate is unchanged by the
``by_regime`` pass, and assert exact exclusion counts for trades whose
originating firing carried no regime tag.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from apps.backtesting.domain.metrics import (
    calculate_max_drawdown,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
)
from apps.backtesting.services import BacktestStatsService

_BASE = datetime(2026, 6, 10, 7, 0, 0, tzinfo=timezone.utc)


@pytest.mark.django_db
class TestRegimePerformance:
    """Exact-value tests for the regime-conditioned stats pass."""

    def _create_trade(
        self,
        run,
        side: str,
        entry: str,
        fill: str,
        qty: int,
        regime: str | None,
        created_at: datetime,
    ) -> None:
        """Insert one filled order (and its fill/rule-execution rows).

        ``regime=None`` simulates a firing with no regime tag: no
        ``RuleExecution`` row is written, so the trade is unattributable.
        """
        from apps.execution.infrastructure.models import ExecutionRequest, Fill, Order
        from apps.rule_engine.infrastructure.models import RuleExecution

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
        # the equity-curve ordering and IS/OOS split are deterministic.
        Order.objects.filter(id=order.id).update(created_at=created_at)
        Fill.objects.create(
            order=order,
            sequence=1,
            quantity=Decimal(qty),
            price=Decimal(fill),
            occurred_at=created_at,
        )
        if regime is not None:
            RuleExecution.objects.create(
                rule_id="long_momentum_v1",
                symbol="RELIANCE",
                severity="medium",
                trigger_data={"regime": regime},
                analysis_event_id=corr,
            )

    def _zero_cost_run(self, backtest_run) -> None:
        """Zero commission/slippage so net P&L equals raw P&L (clean math)."""
        backtest_run.commission_rate = Decimal("0")
        backtest_run.slippage_bps = Decimal("0")
        backtest_run.save()

    def _seed_three_regimes(self, run) -> None:
        # BULLISH: two winners -> +1000, +500 (gross profit 1500)
        self._create_trade(run, "LONG", "100.00", "110.00", 100, "BULLISH", _BASE)
        self._create_trade(
            run, "LONG", "50.00", "55.00", 100, "BULLISH", _BASE + timedelta(seconds=1)
        )
        # BEARISH: two losers -> -1000, -500 (gross loss 1500)
        self._create_trade(
            run, "SHORT", "200.00", "210.00", 100, "BEARISH", _BASE + timedelta(seconds=2)
        )
        self._create_trade(
            run, "SHORT", "100.00", "105.00", 100, "BEARISH", _BASE + timedelta(seconds=3)
        )
        # RANGING: one winner -> +250
        self._create_trade(
            run, "LONG", "100.00", "102.50", 100, "RANGING", _BASE + timedelta(seconds=4)
        )

    def test_by_regime_matches_hand_computed_values(self, backtest_run) -> None:
        self._zero_cost_run(backtest_run)
        self._seed_three_regimes(backtest_run)

        stats = BacktestStatsService().run_stats(backtest_run)
        assert Decimal(stats["equity_at_completion"]) == Decimal("1000000")
        e = Decimal(stats["equity_at_completion"])

        # -- Unconditioned aggregate is exactly the hand-computed baseline; the
        # by_regime pass must not perturb it (regression guard, per package P).
        assert stats["trade_count"] == 5
        assert stats["fill_count"] == 5
        assert stats["win_count"] == 3
        assert stats["loss_count"] == 2
        assert Decimal(stats["gross_profit"]) == Decimal("1750")
        assert Decimal(stats["gross_loss"]) == Decimal("1500")
        assert Decimal(stats["total_transaction_costs"]) == Decimal("0")
        assert Decimal(stats["total_slippage_impact"]) == Decimal("0")
        assert Decimal(stats["net_pnl"]) == Decimal("250")
        assert Decimal(stats["win_rate"]) == Decimal("0.6")
        assert Decimal(stats["expectancy"]) == Decimal("50.0")
        assert Decimal(stats["profit_factor"]) == Decimal("1750") / Decimal("1500")

        global_curve = [e, e + 1000, e + 1500, e + 500, e, e + 250]
        global_returns = [
            Decimal("1000") / e,
            Decimal("500") / (e + Decimal("1000")),
            Decimal("-1000") / (e + Decimal("1500")),
            Decimal("-500") / (e + Decimal("500")),
            Decimal("250") / e,
        ]
        global_max_dd_pct, _ = calculate_max_drawdown(global_curve)
        assert Decimal(stats["max_drawdown_pct"]) == global_max_dd_pct
        assert Decimal(stats["sharpe_ratio"]) == calculate_sharpe_ratio(global_returns)
        assert Decimal(stats["sortino_ratio"]) == calculate_sortino_ratio(global_returns)

        # -- BULLISH: 2 winners.
        bull = stats["by_regime"]["BULLISH"]
        assert bull["trade_count"] == 2
        assert bull["win_count"] == 2
        assert bull["loss_count"] == 0
        assert Decimal(bull["gross_profit"]) == Decimal("1500")
        assert Decimal(bull["gross_loss"]) == Decimal("0")
        assert Decimal(bull["net_pnl"]) == Decimal("1500")
        assert Decimal(bull["win_rate"]) == Decimal("1.0")
        assert Decimal(bull["avg_win"]) == Decimal("750")
        assert Decimal(bull["expectancy"]) == Decimal("750")
        assert Decimal(bull["profit_factor"]) == Decimal("999.99")
        assert Decimal(bull["max_drawdown_pct"]) == Decimal("0")
        assert bull["sortino_ratio"] is None  # no downside returns at all
        bull_returns = [
            Decimal("1000") / e,
            Decimal("500") / (e + Decimal("1000")),
        ]
        assert Decimal(bull["sharpe_ratio"]) == calculate_sharpe_ratio(bull_returns)

        # -- BEARISH: 2 losers.
        bear = stats["by_regime"]["BEARISH"]
        assert bear["trade_count"] == 2
        assert bear["win_count"] == 0
        assert bear["loss_count"] == 2
        assert Decimal(bear["gross_profit"]) == Decimal("0")
        assert Decimal(bear["gross_loss"]) == Decimal("1500")
        assert Decimal(bear["net_pnl"]) == Decimal("-1500")
        assert Decimal(bear["win_rate"]) == Decimal("0")
        assert Decimal(bear["avg_loss"]) == Decimal("750")
        assert Decimal(bear["expectancy"]) == Decimal("-750")
        assert Decimal(bear["profit_factor"]) == Decimal("0")
        assert Decimal(bear["max_drawdown_pct"]) == Decimal("0.15")
        assert Decimal(bear["max_drawdown_amount"]) == Decimal("1500")
        bear_returns = [
            Decimal("-1000") / e,
            Decimal("-500") / (e - Decimal("1000")),
        ]
        assert Decimal(bear["sharpe_ratio"]) == calculate_sharpe_ratio(bear_returns)
        assert Decimal(bear["sortino_ratio"]) == calculate_sortino_ratio(bear_returns)

        # -- RANGING: single winner -> no sharpe/sortino samples.
        rang = stats["by_regime"]["RANGING"]
        assert rang["trade_count"] == 1
        assert rang["win_count"] == 1
        assert Decimal(rang["gross_profit"]) == Decimal("250")
        assert Decimal(rang["net_pnl"]) == Decimal("250")
        assert Decimal(rang["win_rate"]) == Decimal("1.0")
        assert Decimal(rang["expectancy"]) == Decimal("250")
        assert Decimal(rang["profit_factor"]) == Decimal("999.99")
        assert Decimal(rang["max_drawdown_pct"]) == Decimal("0")
        assert rang["sharpe_ratio"] is None
        assert rang["sortino_ratio"] is None

        assert stats["missing_regime_count"] == 0
        assert set(stats["by_regime"]) == {"BULLISH", "BEARISH", "RANGING"}

    def test_unregime_tagged_trade_excluded_from_by_regime_only(self, backtest_run) -> None:
        self._zero_cost_run(backtest_run)
        # One trade with a regime tag (+1000 win), one without (-500 loss).
        self._create_trade(
            run=backtest_run,
            side="LONG",
            entry="100.00",
            fill="110.00",
            qty=100,
            regime="BULLISH",
            created_at=_BASE,
        )
        self._create_trade(
            run=backtest_run,
            side="LONG",
            entry="50.00",
            fill="45.00",
            qty=100,
            regime=None,
            created_at=_BASE + timedelta(seconds=1),
        )

        stats = BacktestStatsService().run_stats(backtest_run)

        # The untagged trade is absent from every regime bucket but fully
        # present in the unconditioned aggregate.
        assert stats["trade_count"] == 2
        assert stats["missing_regime_count"] == 1
        assert set(stats["by_regime"]) == {"BULLISH"}
        assert stats["by_regime"]["BULLISH"]["trade_count"] == 1
        assert stats["win_count"] == 1
        assert stats["loss_count"] == 1
        assert Decimal(stats["net_pnl"]) == Decimal("500")
        assert sum(b["trade_count"] for b in stats["by_regime"].values()) == 1

    def test_run_stats_is_idempotent(self, backtest_run) -> None:
        self._zero_cost_run(backtest_run)
        self._seed_three_regimes(backtest_run)

        first = BacktestStatsService().run_stats(backtest_run)
        second = BacktestStatsService().run_stats(backtest_run)
        assert first == second
        assert first["by_regime"] == second["by_regime"]
