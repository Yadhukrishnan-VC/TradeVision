"""Risk Sophistication batch — NSE execution cost model tests.

Known-answer tests pin the model against hand-computed NSE statutory costs for
a deterministic order, so the "realistic cost function" claim is provable
rather than asserted from the implementation itself. Also verifies the
size-dependent impact leg and the BacktestStatsService wiring (opt-in via
``BACKTEST_COST_MODEL=nse``).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.backtesting.domain.nse_costs import (
    NseCostModel,
    compute_trade_cost,
    impact_bps_for,
    nse_cost_model_from_settings,
)

_MODEL = NseCostModel(product="delivery")


class TestComputeTradeCost:
    def test_delivery_buy_breakdown(self) -> None:
        """Hand-computed: 10 shares @ 1000 = 10000 notional, delivery BUY.

        stt = 0 (sell side only)
        brokerage = 20 (flat)
        exchange = 10000 * 0.0000297 = 0.297
        sebi     = 10000 * 0.000001 = 0.01
        stamp    = 10000 * 0.00015 = 1.5 (buy side)
        gst      = 0.18 * (20 + 0.297 + 0.01) = 3.65526
        impact   = 10000 * 5bps / 10000 = 5 (notional <= reference ADV)
        total    = 0 + 20 + 0.297 + 0.01 + 1.5 + 3.65526 + 5 = 30.46226
        """
        result = compute_trade_cost(
            quantity=Decimal(10),
            price=Decimal(1000),
            side="LONG",
            model=_MODEL,
        )
        assert result["stt"] == Decimal(0)
        assert result["brokerage"] == Decimal("20")
        assert result["exchange_charges"] == Decimal("0.297")
        assert result["sebi_fee"] == Decimal("0.01")
        assert result["stamp_duty"] == Decimal("1.5")
        assert result["gst"] == Decimal("3.65526")
        assert result["impact_cost"] == Decimal("5")
        assert result["total"] == Decimal("30.46226")

    def test_delivery_sell_adds_stt(self) -> None:
        """10 shares @ 1000 delivery SELL adds 0.1% STT = 10, no stamp duty.

        total = 10 (stt) + 20 (brokerage) + 0.297 + 0.01 + 0 (stamp) +
                3.65526 (gst) + 5 (impact) = 38.96226
        """
        result = compute_trade_cost(
            quantity=Decimal(10),
            price=Decimal(1000),
            side="SHORT",
            model=_MODEL,
        )
        assert result["stt"] == Decimal("10")
        assert result["stamp_duty"] == Decimal(0)
        assert result["total"] == Decimal("38.96226")

    def test_intraday_rates_apply(self) -> None:
        model = NseCostModel(product="intraday")
        result = compute_trade_cost(
            quantity=Decimal(10),
            price=Decimal(1000),
            side="SELL",
            model=model,
        )
        assert result["stt"] == Decimal("2.5")  # 0.025% sell
        assert result["stamp_duty"] == Decimal(0)

    def test_brokerage_percentage_alternative(self) -> None:
        model = NseCostModel(product="delivery", brokerage_pct=Decimal("0.001"))
        result = compute_trade_cost(
            quantity=Decimal(10),
            price=Decimal(1000),
            side="LONG",
            model=model,
        )
        assert result["brokerage"] == Decimal("10")


class TestImpactScaling:
    def test_impact_scales_with_size_relative_to_adv(self) -> None:
        model = NseCostModel(product="delivery", impact_reference_adv=Decimal("1000000"))
        small = impact_bps_for(model, Decimal("500000"))
        large = impact_bps_for(model, Decimal("5000000"))
        assert small == Decimal("5")  # below/at ADV -> base
        assert large == Decimal("25")  # 5x ADV -> capped at 5x base

    def test_impact_capped_at_max_multiple(self) -> None:
        model = NseCostModel(
            product="delivery",
            impact_reference_adv=Decimal("1000000"),
            impact_max_multiple=Decimal("3"),
        )
        assert impact_bps_for(model, Decimal("50000000")) == Decimal("15")


class TestModelFromSettings:
    def test_defaults_when_settings_empty(self, settings) -> None:
        settings.BACKTEST_NSE_COST_MODEL = {}
        model = nse_cost_model_from_settings()
        assert model.product == "delivery"
        assert model.stt_sell_rate == Decimal("0.001")
        assert model.brokerage_per_order == Decimal("20")


@pytest.mark.django_db
class TestNseWiringIntoBacktestStats:
    def _seed(self, run) -> None:
        import uuid as _uuid
        from datetime import datetime, timezone

        from apps.execution.infrastructure.models import ExecutionRequest, Fill, Order
        from apps.rule_engine.infrastructure.models import RuleExecution

        account_id = run.account_id
        correlation_id = _uuid.uuid4()
        req = ExecutionRequest.objects.create(
            idempotency_key=f"nse-{correlation_id}",
            account_id=account_id,
            symbol="RELIANCE",
            side="LONG",
            quantity=Decimal(10),
            entry_price=Decimal(1000),
            stop_loss=Decimal(900),
            correlation_id=correlation_id,
            risk_approved_event_id=_uuid.uuid4(),
            rule_id="long_momentum_v1",
            event_type="BREAKOUT",
            status="FILLED",
        )
        order = Order.objects.create(
            execution_request=req,
            account_id=account_id,
            symbol="RELIANCE",
            side="LONG",
            quantity=Decimal(10),
            status="FILLED",
            filled_quantity=Decimal(10),
            avg_fill_price=Decimal(1000),
            entry_price=Decimal(1000),
            stop_loss=Decimal(900),
            correlation_id=correlation_id,
        )
        Fill.objects.create(
            order=order,
            sequence=1,
            quantity=Decimal(10),
            price=Decimal(1000),
            occurred_at=datetime(2024, 1, 20, tzinfo=timezone.utc),
        )
        RuleExecution.objects.create(
            analysis_event_id=correlation_id,
            symbol="RELIANCE",
            rule_id="long_momentum_v1",
            severity="info",
            trigger_data={"mode": "backtest", "regime": "trending"},
        )

    def _stats(self, run):
        from apps.backtesting.services import BacktestStatsService

        return BacktestStatsService().run_stats(run)

    def test_flat_path_unchanged_by_default(self, backtest_run, settings) -> None:
        self._seed(backtest_run)
        settings.BACKTEST_COST_MODEL = "flat"
        stats = self._stats(backtest_run)
        # Flat path unchanged: default run commission 0.0003 + slippage 5bps
        # => 10*1000*0.0003 + 10*1000*(5/10000) = 3 + 5 = 8.
        assert Decimal(stats["total_transaction_costs"]) == Decimal("8.0")
        assert Decimal(stats["total_slippage_impact"]) == Decimal("5.0")

    def test_nse_path_applies_realistic_costs(self, backtest_run, settings) -> None:
        self._seed(backtest_run)
        settings.BACKTEST_COST_MODEL = "nse"
        settings.BACKTEST_NSE_COST_MODEL = {}
        stats = self._stats(backtest_run)
        expected_total = compute_trade_cost(
            quantity=Decimal(10),
            price=Decimal(1000),
            side="LONG",
            model=nse_cost_model_from_settings(),
        )["total"]
        assert Decimal(stats["total_transaction_costs"]) == expected_total
        assert Decimal(stats["total_transaction_costs"]) > Decimal(0)