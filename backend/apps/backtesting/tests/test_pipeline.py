"""Batch M3 — historical replay end-to-end pipeline tests.

The runner replays a historical ``TASnapshot`` through the *real* event chain
(TechnicalAnalysisIngestionService -> EventBus -> intelligence -> rule_engine
-> risk_management -> execution -> PaperBroker). These tests prove:

* market-hours and freshness checks evaluate against the simulated historical
  reference time rather than the wall clock,
* the resulting order and fill land on the run's isolated account (never the
  ``is_default`` account),
* the fill's ``occurred_at`` is the historical bar timestamp,
* a completed run is a no-op on re-delivery.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from apps.backtesting.models import BacktestRunStatus
from apps.backtesting.services import BacktestRunnerService, BacktestStatsService
from apps.backtesting.tests.conftest import HISTORICAL_BAR_TIME

pytestmark = pytest.mark.django_db


class TestHistoricalGateways:
    def test_historical_market_hours_evaluation(self) -> None:
        from apps.risk_management.gateways.market_calendar_status_gateway import (
            MarketCalendarStatusGateway,
        )
        from core.clock import bind_simulated_time, get_clock

        gateway = MarketCalendarStatusGateway()
        # 2024-06-10 07:00 UTC == 12:30 IST, a trading Monday in market hours.
        with bind_simulated_time(HISTORICAL_BAR_TIME):
            assert get_clock().now() == HISTORICAL_BAR_TIME
            assert gateway.is_market_open(get_clock().now()) is True

        # 2024-06-10 20:00 UTC == 01:30 IST the next day -> after close.
        closed = datetime(2024, 6, 10, 20, 0, 0, tzinfo=timezone.utc)
        with bind_simulated_time(closed):
            assert gateway.is_market_open(get_clock().now()) is False

        # 2024-06-10 03:00 UTC == 08:30 IST -> before pre-open, closed.
        pre = datetime(2024, 6, 10, 3, 0, 0, tzinfo=timezone.utc)
        with bind_simulated_time(pre):
            assert gateway.is_market_open(get_clock().now()) is False

    def test_historical_freshness_evaluation(self) -> None:
        from apps.risk_management.gateways.market_calendar_status_gateway import (
            MarketCalendarStatusGateway,
        )
        from core.clock import bind_simulated_time, get_clock

        gateway = MarketCalendarStatusGateway()
        threshold = 120  # TICK_FRESHNESS_THRESHOLD_SECONDS
        with bind_simulated_time(HISTORICAL_BAR_TIME):
            reference = get_clock().now()
            # Fresh: occurred within the threshold of the historical reference.
            assert (
                gateway.is_fresh(reference - timedelta(seconds=threshold), reference)
                is True
            )
            # Stale: older than the threshold, judged against the historical ref.
            assert (
                gateway.is_fresh(reference - timedelta(seconds=threshold + 1), reference)
                is False
            )
            assert (
                gateway.is_fresh(reference - timedelta(minutes=10), reference) is False
            )


class TestHistoricalReplayPipeline:
    def test_full_chain_replay_routes_to_isolated_account(
        self,
        seed_session_facts,
        register_all_handlers,
        active_bus,
        historical_snapshot,
        backtest_run,
        default_account,
    ) -> None:
        register_all_handlers(active_bus)

        result = BacktestRunnerService().run(backtest_run.id)

        assert result["status"] == "COMPLETED"
        assert result["bars_processed"] == "1"
        backtest_run.refresh_from_db()
        assert backtest_run.status == BacktestRunStatus.COMPLETED
        assert backtest_run.last_processed_snapshot_id == historical_snapshot.id

        # Rule + risk fired on the chain. VolumeSpikeRule also legitimately
        # fires (1M bar vs 100K 20-day average); the risk layer rejects it
        # (MISSING_STOP_LOSS) and approves the long momentum setup.
        rule_fired = [
            e
            for e in active_bus.published_events
            if e.event_type == "rule_engine.RuleFired"
            and e.payload["rule_id"] == "long_momentum_v1"
        ]
        assert len(rule_fired) == 1
        assert rule_fired[0].payload["account_id"] == str(backtest_run.account_id)

        risk_approved = [
            e
            for e in active_bus.published_events
            if e.event_type == "risk_management.RiskApproved"
        ]
        assert len(risk_approved) == 1
        assert risk_approved[0].payload["account_id"] == str(backtest_run.account_id)

        # The order and its request land on the isolated account.
        from apps.execution.infrastructure.models import ExecutionRequest, Fill, Order

        order = Order.objects.get(account_id=backtest_run.account_id)
        assert order.symbol == "RELIANCE"
        assert order.side == "LONG"
        assert order.status == "FILLED"
        assert order.correlation_id is not None
        assert order.execution_request.account_id == backtest_run.account_id

        fill = Fill.objects.get(order_id=order.id)
        assert fill.quantity == order.quantity
        assert fill.occurred_at == HISTORICAL_BAR_TIME

        # Isolation: the production default account is untouched.
        assert Order.objects.filter(account_id=default_account.id).count() == 0
        assert ExecutionRequest.objects.filter(account_id=default_account.id).count() == 0

    def test_fill_and_order_timestamps_use_historical_time(
        self,
        seed_session_facts,
        register_all_handlers,
        active_bus,
        historical_snapshot,
        backtest_run,
    ) -> None:
        register_all_handlers(active_bus)
        BacktestRunnerService().run(backtest_run.id)

        from apps.execution.infrastructure.models import Fill, Order

        order = Order.objects.get(account_id=backtest_run.account_id)
        assert order.created_at != HISTORICAL_BAR_TIME  # wall clock for audit rows
        fill = Fill.objects.get(order_id=order.id)
        assert fill.occurred_at == HISTORICAL_BAR_TIME

    def test_stats_after_replay(
        self,
        seed_session_facts,
        register_all_handlers,
        active_bus,
        historical_snapshot,
        backtest_run,
    ) -> None:
        register_all_handlers(active_bus)
        BacktestRunnerService().run(backtest_run.id)
        backtest_run.refresh_from_db()

        stats = BacktestStatsService().run_stats(backtest_run)
        assert stats["status"] == "COMPLETED"
        assert stats["trade_count"] == 1
        assert stats["fill_count"] == 1
        assert stats["trades"][0]["symbol"] == "RELIANCE"
        assert stats["trades"][0]["status"] == "FILLED"
        # Capital shrank by the notional (1,000,000 - 103 * 3333).
        from decimal import Decimal

        assert Decimal(stats["available_capital"]) == Decimal("1000000") - Decimal("343299")

    def test_redelivery_is_a_noop(
        self,
        seed_session_facts,
        register_all_handlers,
        active_bus,
        historical_snapshot,
        backtest_run,
    ) -> None:
        register_all_handlers(active_bus)
        from apps.execution.infrastructure.models import Order

        first = BacktestRunnerService().run(backtest_run.id)
        assert first["status"] == "COMPLETED"
        assert Order.objects.filter(account_id=backtest_run.account_id).count() == 1

        # A redelivered run produces no new records.
        second = BacktestRunnerService().run(backtest_run.id)
        assert second["status"] == "ALREADY_COMPLETED"
        assert Order.objects.filter(account_id=backtest_run.account_id).count() == 1

        from apps.execution.infrastructure.models import Fill

        assert Fill.objects.filter(order__account_id=backtest_run.account_id).count() == 1


class TestResumeAfterFailure:
    def test_failed_run_resumes_without_replaying_consumed_bars(
        self, seed_session_facts, register_all_handlers, active_bus, backtest_run
    ) -> None:
        from apps.backtesting.tests.conftest import _make_ta_payload
        from apps.technical_analysis.infrastructure.models import TASnapshot

        register_all_handlers(active_bus)

        t1 = datetime(2024, 6, 10, 5, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 6, 10, 7, 0, 0, tzinfo=timezone.utc)

        TASnapshot.objects.create(
            symbol="RELIANCE",
            exchange="NSE",
            timeframe="1D",
            pine_id="long_momentum@tv",
            pine_version="5",
            indicators={"vwap": "101.50", "ema_20": "102.00"},
            raw_payload=_make_ta_payload(),
            snapshot_timestamp=t1,
        )
        TASnapshot.objects.create(
            symbol="RELIANCE",
            exchange="NSE",
            timeframe="1D",
            pine_id="long_momentum@tv",
            pine_version="5",
            indicators={"vwap": "101.50", "ema_20": "102.00"},
            raw_payload={},  # invalid: missing required 'close'
            snapshot_timestamp=t2,
        )

        result = BacktestRunnerService().run(backtest_run.id)
        assert result["status"] == "FAILED"
        backtest_run.refresh_from_db()
        assert backtest_run.status == BacktestRunStatus.FAILED
        # The cursor points at the last successfully consumed bar (t1).
        assert backtest_run.last_processed_snapshot_id is not None

        from apps.execution.infrastructure.models import Order

        orders_before_resume = Order.objects.filter(
            account_id=backtest_run.account_id
        ).count()

        # Fix the bad payload and resume: only the un-consumed bar replays.
        bad = TASnapshot.objects.get(snapshot_timestamp=t2)
        bad.raw_payload = _make_ta_payload()
        bad.save()
        resumed = BacktestRunnerService().run(backtest_run.id)
        assert resumed["status"] == "COMPLETED"
        assert resumed["bars_processed"] == "1"

        from apps.execution.infrastructure.models import Fill

        assert (
            Order.objects.filter(account_id=backtest_run.account_id).count()
            == orders_before_resume + 1
        )
        assert (
            Fill.objects.filter(order__account_id=backtest_run.account_id).count()
            == orders_before_resume + 1
        )


class TestMultiBarReplay:
    def test_multi_bar_replay_produces_independent_chains(
        self,
        seed_session_facts,
        register_all_handlers,
        active_bus,
        backtest_run,
        default_account,
        monkeypatch,
    ) -> None:
        from apps.backtesting.services import _correlation_id_for
        from apps.backtesting.tests.conftest import _make_ta_payload
        from apps.execution.infrastructure.models import ExecutionRequest, Fill, Order
        from apps.portfolio.infrastructure.price_source import (
            MarketDataCurrentPriceProvider,
        )
        from apps.technical_analysis.infrastructure.models import TASnapshot

        register_all_handlers(active_bus)

        # Deterministic mark-to-market: no cached quote means the exposure and
        # unrealized-P&L math falls back to each position's average entry price
        # (the production path when a quote is unavailable). Without this the
        # exposure cap decision would depend on leftover quote keys in Redis.
        monkeypatch.setattr(
            MarketDataCurrentPriceProvider,
            "get_current_price",
            lambda self, symbol: None,
        )

        bars = (
            datetime(2024, 6, 10, 5, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 6, 10, 6, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 6, 10, 7, 0, 0, tzinfo=timezone.utc),
        )
        snapshot_ids = []
        for bar_time in bars:
            snapshot = TASnapshot.objects.create(
                symbol="RELIANCE",
                exchange="NSE",
                timeframe="1D",
                pine_id="long_momentum@tv",
                pine_version="5",
                indicators={"vwap": "101.50", "ema_20": "102.00"},
                raw_payload=_make_ta_payload(),
                snapshot_timestamp=bar_time,
            )
            snapshot_ids.append(snapshot.id)

        result = BacktestRunnerService().run(backtest_run.id)
        assert result["status"] == "COMPLETED"
        assert result["bars_processed"] == "3"

        # One distinct RuleFired chain per bar, all routed to the run's account.
        rule_fired = [
            e
            for e in active_bus.published_events
            if e.event_type == "rule_engine.RuleFired"
            and e.payload["rule_id"] == "long_momentum_v1"
        ]
        assert len(rule_fired) == 3
        assert len({e.event_id for e in rule_fired}) == 3
        assert len({e.correlation_id for e in rule_fired}) == 3
        assert all(
            e.payload["account_id"] == str(backtest_run.account_id)
            for e in rule_fired
        )

        risk_approved = [
            e
            for e in active_bus.published_events
            if e.event_type == "risk_management.RiskApproved"
        ]
        assert len(risk_approved) == 3
        assert len({e.event_id for e in risk_approved}) == 3
        assert all(
            e.payload["account_id"] == str(backtest_run.account_id)
            for e in risk_approved
        )

        # One attributable order + fill per bar. Each bar's intelligence
        # packet carries the deterministic (run_id, snapshot_id) correlation
        # id, and every order in the chain is traceable to exactly one bar's
        # packet event.
        packet_events = [
            e
            for e in active_bus.published_events
            if e.event_type == "intelligence.PacketBuilt"
        ]
        assert len(packet_events) == 3
        assert len({e.event_id for e in packet_events}) == 3
        assert {e.correlation_id for e in packet_events} == {
            _correlation_id_for(backtest_run.id, snapshot_id)
            for snapshot_id in snapshot_ids
        }

        orders = list(
            Order.objects.filter(account_id=backtest_run.account_id).order_by(
                "created_at"
            )
        )
        assert len(orders) == 3
        assert {o.correlation_id for o in orders} == {
            e.event_id for e in packet_events
        }
        assert {e.correlation_id for e in risk_approved} == {
            e.event_id for e in packet_events
        }
        assert len({o.execution_request_id for o in orders}) == 3
        assert all(o.status == "FILLED" for o in orders)
        assert all(
            o.execution_request.account_id == backtest_run.account_id for o in orders
        )
        for order in orders:
            fill = Fill.objects.get(order_id=order.id)
            assert fill.quantity == order.quantity

        assert (
            Fill.objects.filter(order__account_id=backtest_run.account_id).count()
            == 3
        )

        # Isolation: the production default account is untouched by every bar.
        assert Order.objects.filter(account_id=default_account.id).count() == 0
        assert ExecutionRequest.objects.filter(account_id=default_account.id).count() == 0


class TestReproducibility:
    def test_reproducibility_across_independent_runs(
        self,
        seed_session_facts,
        register_all_handlers,
        active_bus,
        historical_snapshot,
        backtest_run,
        default_account,
        monkeypatch,
        django_user_model,
    ) -> None:
        from datetime import datetime, timezone
        from decimal import Decimal
        from uuid import uuid4

        from apps.accounts.infrastructure.models import Account
        from apps.backtesting.models import BacktestRun
        from apps.execution.infrastructure.models import ExecutionRequest, Fill, Order
        from apps.portfolio.application.capital_service import CapitalService
        from apps.portfolio.infrastructure.models import AccountCapitalState
        from apps.portfolio.infrastructure.price_source import (
            MarketDataCurrentPriceProvider,
        )

        register_all_handlers(active_bus)

        monkeypatch.setattr(
            MarketDataCurrentPriceProvider,
            "get_current_price",
            lambda self, symbol: None,
        )

        # ``BacktestRun.account_id`` is unique, so the second independent run
        # needs its own identically-funded account.
        second_user = django_user_model.objects.create_user(
            username=f"bt_repro_{uuid4().hex[:8]}", password="p"
        )
        second_account = Account.objects.create(
            name=f"Backtest {second_user.username}",
            owner=second_user,
            is_default=False,
        )
        CapitalService().deposit(second_account.id, Decimal("1000000"))

        second_run = BacktestRun(
            symbol="RELIANCE",
            timeframe="1D",
            range_start=datetime(2024, 6, 9, tzinfo=timezone.utc),
            range_end=datetime(2024, 6, 11, tzinfo=timezone.utc),
            account=second_account,
            status="PENDING",
        )
        second_run.save()

        first = BacktestRunnerService().run(backtest_run.id)
        second = BacktestRunnerService().run(second_run.id)
        assert first["status"] == "COMPLETED"
        assert second["status"] == "COMPLETED"
        assert first["bars_processed"] == second["bars_processed"] == "1"

        def _long_momentum_fired(account_id):
            return [
                e
                for e in active_bus.published_events
                if e.event_type == "rule_engine.RuleFired"
                and e.payload["rule_id"] == "long_momentum_v1"
                and e.payload["account_id"] == str(account_id)
            ]

        first_fired = _long_momentum_fired(backtest_run.account_id)
        second_fired = _long_momentum_fired(second_run.account_id)
        assert len(first_fired) == len(second_fired) == 1
        for key in ("entry_price", "stop_loss", "volume_ratio"):
            assert first_fired[0].payload["trigger_data"][key] == second_fired[0].payload[
                "trigger_data"
            ][key]

        def _risk_approved(account_id):
            return [
                e
                for e in active_bus.published_events
                if e.event_type == "risk_management.RiskApproved"
                and e.payload["account_id"] == str(account_id)
            ]

        first_approved = _risk_approved(backtest_run.account_id)
        second_approved = _risk_approved(second_run.account_id)
        assert len(first_approved) == len(second_approved) == 1
        for key in ("entry_price", "stop_loss", "position_size"):
            assert first_approved[0].payload[key] == second_approved[0].payload[key]

        first_order = Order.objects.get(account_id=backtest_run.account_id)
        second_order = Order.objects.get(account_id=second_run.account_id)
        assert first_order.side == second_order.side == "LONG"
        assert first_order.quantity == second_order.quantity
        assert first_order.entry_price == second_order.entry_price
        assert first_order.avg_fill_price == second_order.avg_fill_price
        assert first_order.filled_quantity == second_order.filled_quantity
        assert first_order.execution_request.rule_id == "long_momentum_v1"
        assert (
            first_order.execution_request.rule_id
            == second_order.execution_request.rule_id
        )

        first_fill = Fill.objects.get(order_id=first_order.id)
        second_fill = Fill.objects.get(order_id=second_order.id)
        assert first_fill.quantity == second_fill.quantity
        assert first_fill.price == second_fill.price

        first_capital = AccountCapitalState.objects.get(
            account_id=backtest_run.account_id
        )
        second_capital = AccountCapitalState.objects.get(account_id=second_run.account_id)
        assert first_capital.equity == second_capital.equity
        assert first_capital.available_capital == second_capital.available_capital
        assert first_capital.realized_pnl_today == second_capital.realized_pnl_today

        # The production default account is untouched by either run.
        assert Order.objects.filter(account_id=default_account.id).count() == 0
        assert ExecutionRequest.objects.filter(account_id=default_account.id).count() == 0
