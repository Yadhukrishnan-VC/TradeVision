"""⚠️ SYNTHETIC SMOKE TEST — NOT EDGE EVIDENCE — machinery only.

This file exists ONLY to confirm the edge-validation pipeline (single-run +
walk-forward + cost-sensitivity + shuffled-baseline significance) executes
end-to-end without error: imports resolve, no crashes, output schema is
well-formed. It replays TA snapshots built from the OHLCV of the 10 synthetic
candles currently stored in the dev databases (the readiness-batch `paper`
backfill output) — **not** real market data.

Nothing below asserts any performance magnitude, and nothing in this module
ever reads or writes ``RuleConfig.validated_regimes``. Every number this
pipeline produces on this dataset is meaningless as edge evidence.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time, timezone
from decimal import Decimal

import pytest

from apps.accounts.infrastructure.models import Account
from apps.backtesting.application.cost_sensitivity_service import CostSensitivityService
from apps.backtesting.application.edge_validation_service import EdgeValidationService
from apps.backtesting.application.walk_forward_service import WalkForwardService
from apps.backtesting.domain.attribution import group_fills_by_rule
from apps.backtesting.domain.significance import shuffled_baseline_significance
from apps.backtesting.infrastructure.rule_attribution_repository import (
    RuleAttributionRepository,
)
from apps.backtesting.models import BacktestRun
from apps.backtesting.services import BacktestRunnerService
from apps.portfolio.application.capital_service import CapitalService

_UTC = timezone.utc

#: The 10 synthetic candles stored in the dev DBs by the readiness batch
#: (NSE:RELIANCE token 12345, NSE:INFY token 67890, 1D, 2026-08-14..18).
#: (symbol, exchange, date, open, high, low, close, volume)
SYNTHETIC_CANDLES: list[tuple[str, str, datetime, str, str, str, str, int]] = [
    (
        "RELIANCE",
        "NSE",
        datetime(2026, 8, 14, tzinfo=_UTC),
        "2265.00",
        "2271.34",
        "2258.66",
        "2268.17",
        124438,
    ),
    (
        "RELIANCE",
        "NSE",
        datetime(2026, 8, 15, tzinfo=_UTC),
        "2268.17",
        "2276.34",
        "2260.00",
        "2272.25",
        462392,
    ),
    (
        "RELIANCE",
        "NSE",
        datetime(2026, 8, 16, tzinfo=_UTC),
        "2272.25",
        "2277.70",
        "2266.80",
        "2269.52",
        111600,
    ),
    (
        "RELIANCE",
        "NSE",
        datetime(2026, 8, 17, tzinfo=_UTC),
        "2269.52",
        "2289.95",
        "2249.09",
        "2259.31",
        41545,
    ),
    (
        "RELIANCE",
        "NSE",
        datetime(2026, 8, 18, tzinfo=_UTC),
        "2259.31",
        "2299.07",
        "2219.55",
        "2239.43",
        297296,
    ),
    (
        "INFY",
        "NSE",
        datetime(2026, 8, 14, tzinfo=_UTC),
        "2224.00",
        "2245.35",
        "2202.65",
        "2234.68",
        486180,
    ),
    (
        "INFY",
        "NSE",
        datetime(2026, 8, 15, tzinfo=_UTC),
        "2234.68",
        "2274.46",
        "2194.90",
        "2254.57",
        117014,
    ),
    (
        "INFY",
        "NSE",
        datetime(2026, 8, 16, tzinfo=_UTC),
        "2254.57",
        "2271.70",
        "2237.44",
        "2263.14",
        335742,
    ),
    (
        "INFY",
        "NSE",
        datetime(2026, 8, 17, tzinfo=_UTC),
        "2263.14",
        "2287.58",
        "2238.70",
        "2275.36",
        139754,
    ),
    (
        "INFY",
        "NSE",
        datetime(2026, 8, 18, tzinfo=_UTC),
        "2275.36",
        "2315.41",
        "2235.31",
        "2295.38",
        27525,
    ),
]

_RANGE_START = datetime(2026, 8, 14, tzinfo=_UTC)
_RANGE_END = datetime(2026, 8, 19, tzinfo=_UTC)


def _seed_snapshots() -> None:
    """TA snapshot rows derived from the synthetic candles (the candle→TA handoff)."""
    from apps.technical_analysis.infrastructure.models import TASnapshot

    for symbol, exchange, day, open_, high, low, close, volume in SYNTHETIC_CANDLES:
        bar_time = datetime.combine(day.date(), time(7, 0), tzinfo=_UTC)
        indicators = {"vwap": close, "ema_20": close}
        raw_payload = {
            "ticker": symbol,
            "exchange": exchange,
            "timeframe": "1D",
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "vwap": close,
            "ema_20": close,
            "pine_id": "long_momentum@tv",
            "pine_version": "5",
        }
        TASnapshot.objects.create(
            symbol=symbol,
            exchange=exchange,
            timeframe="1D",
            pine_id="long_momentum@tv",
            pine_version="5",
            indicators=indicators,
            raw_payload=raw_payload,
            snapshot_timestamp=bar_time,
        )


def _create_funded_user(django_user_model):
    user = django_user_model.objects.create_user(
        username=f"smoke_{uuid.uuid4().hex[:8]}", password="p"
    )
    account = Account.objects.create(
        name=f"Smoke {user.username}", owner=user, is_default=False
    )
    CapitalService().deposit(account.id, Decimal(1000000))
    return user


def _net_trade_pnl(order, fill, comm_rate: Decimal, slip_bps: Decimal) -> Decimal:
    direction = Decimal(1) if order.side == "LONG" else Decimal(-1)
    qty = Decimal(str(order.filled_quantity))
    avg_fill = Decimal(str(fill.price))
    entry = Decimal(str(order.entry_price))
    cost = qty * avg_fill * (comm_rate + slip_bps / Decimal(10000))
    return direction * qty * (avg_fill - entry) - cost


@pytest.mark.django_db
class TestEdgeValidationPipelineSmoke:
    """PASS/FAIL on pipeline execution — no performance assertions."""

    def test_single_run_and_walk_forward_execute(
        self, seed_session_facts, register_all_handlers, active_bus, django_user_model
    ) -> None:
        register_all_handlers(active_bus)
        _seed_snapshots()
        user = _create_funded_user(django_user_model)

        result = EdgeValidationService().evaluate(
            owner=user,
            symbol="RELIANCE",
            timeframe="1D",
            range_start=_RANGE_START,
            range_end=_RANGE_END,
            window_size_days=3,
            step_size_days=1,
            in_sample_ratio=Decimal("0.50"),
            commission_rate=Decimal("0.0003"),
            slippage_bps=Decimal("5.0"),
            initial_capital=Decimal(1000000),
        )

        assert set(result).issuperset(
            {
                "symbol",
                "single_run",
                "walk_forward",
                "by_rule",
                "edge_criterion",
                "commission_rate",
                "slippage_bps",
            }
        )
        assert result["single_run"]["by_rule"] == result["by_rule"] or isinstance(
            result["single_run"], dict
        )
        assert isinstance(result["by_rule"], dict)
        assert isinstance(result["walk_forward"]["windows"], list)
        assert "distribution" in result["walk_forward"]

    def test_walk_forward_direct_execute(
        self, seed_session_facts, register_all_handlers, active_bus, django_user_model
    ) -> None:
        register_all_handlers(active_bus)
        _seed_snapshots()
        user = _create_funded_user(django_user_model)

        result = WalkForwardService().execute(
            owner=user,
            symbol="RELIANCE",
            timeframe="1D",
            range_start=_RANGE_START,
            range_end=_RANGE_END,
            window_size_days=3,
            step_size_days=1,
            in_sample_ratio=Decimal("0.50"),
            commission_rate=Decimal("0.0003"),
            slippage_bps=Decimal("5.0"),
            initial_capital=Decimal(1000000),
        )
        assert result["symbol"] == "RELIANCE"
        assert result["total_windows"] == 3
        assert "distribution" in result

    def test_cost_sensitivity_executes(
        self, seed_session_facts, register_all_handlers, active_bus, django_user_model
    ) -> None:
        register_all_handlers(active_bus)
        _seed_snapshots()
        user = _create_funded_user(django_user_model)

        result = CostSensitivityService().execute(
            owner=user,
            symbol="RELIANCE",
            timeframe="1D",
            range_start=_RANGE_START,
            range_end=_RANGE_END,
            commission_range=(Decimal("0.0000"), Decimal("0.0004")),
            commission_step=Decimal("0.0002"),
            slippage_range=(Decimal(0), Decimal(10)),
            slippage_step=Decimal(10),
            initial_capital=Decimal(1000000),
        )
        assert isinstance(result["by_rule"], dict)
        for rule_report in result["by_rule"].values():
            assert "breakeven" in rule_report
            assert "series" in rule_report

    def test_significance_wiring_on_run_trades(
        self, seed_session_facts, register_all_handlers, active_bus, django_user_model
    ) -> None:
        register_all_handlers(active_bus)
        _seed_snapshots()
        user = _create_funded_user(django_user_model)
        account = Account.objects.filter(owner=user).first()

        run = BacktestRun(
            symbol="RELIANCE",
            timeframe="1D",
            range_start=_RANGE_START,
            range_end=_RANGE_END,
            account=account,
            status="PENDING",
            commission_rate=Decimal("0.0003"),
            slippage_bps=Decimal("5.0"),
            in_sample_ratio=Decimal("0.50"),
        )
        run.save()
        result = BacktestRunnerService().run(run.id)
        assert result["status"] == "COMPLETED"

        from apps.execution.infrastructure.models import Fill, Order
        from apps.rule_engine.infrastructure.models import RuleExecution

        orders = list(
            Order.objects.filter(account_id=run.account_id).order_by("created_at")
        )
        fills = list(
            Fill.objects.filter(order__account_id=run.account_id).order_by("created_at")
        )
        correlation_ids = {o.correlation_id for o in orders if o.correlation_id}
        rule_executions = RuleAttributionRepository().get_rule_executions(
            correlation_ids
        )
        order_by_id = {str(o.id): o for o in orders}
        fills_by_rule = group_fills_by_rule(fills, rule_executions, order_by_id)

        for rule_fills in fills_by_rule.values():
            seen: set[str] = set()
            trade_pnls: list[Decimal] = []
            for fill in rule_fills:
                order = order_by_id.get(str(fill.order_id))
                if order is None or str(order.id) in seen:
                    continue
                seen.add(str(order.id))
                trade_pnls.append(
                    _net_trade_pnl(order, fill, Decimal("0.0003"), Decimal("5.0"))
                )
            significance = shuffled_baseline_significance(trade_pnls, seed=42)
            assert significance.verdict in ("SIGNIFICANT", "NOT_SIGNIFICANT", None)
            assert significance.n_trades == len(trade_pnls)
            assert significance.reason

        # Regardless of whether any rule fired, the wiring is exercised: an
        # empty trade set must yield the honest INSUFFICIENT_TRADES outcome.
        if not fills_by_rule:
            significance = shuffled_baseline_significance([], seed=42)
            assert significance.verdict is None
            assert significance.reason == "INSUFFICIENT_TRADES"

        assert isinstance(fills_by_rule, dict)
        assert isinstance(RuleExecution.objects.count(), int)
