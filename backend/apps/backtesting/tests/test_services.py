"""Backtest runner service tests.

These exercise the runner in isolation: the real ingestion pipeline is
replaced with a recorder so the tests focus on the runner's contract —
eager-mode guard, run lifecycle, deterministic correlation ids,
chronological replay, cursor-based resume, and failure handling.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from apps.backtesting.models import BacktestRun, BacktestRunStatus
from apps.backtesting.services import (
    BacktestRunnerService,
    BacktestStatsService,
    _correlation_id_for,
)

pytestmark = pytest.mark.django_db


def _seed_snapshot(symbol, timestamp, timeframe="1D", **payload_overrides) -> uuid.UUID:
    from apps.backtesting.tests.conftest import _make_ta_payload
    from apps.technical_analysis.infrastructure.models import TASnapshot

    payload = _make_ta_payload(**payload_overrides)
    snapshot = TASnapshot(
        symbol=symbol,
        exchange="NSE",
        timeframe=timeframe,
        pine_id="long_momentum@tv",
        pine_version="5",
        indicators={"vwap": "101.50", "ema_20": "102.00"},
        raw_payload=payload,
        snapshot_timestamp=timestamp,
    )
    snapshot.save()
    return snapshot.id


def _ingest_recorder(runner):
    """Monkeypatch ``_ingest`` to record the correlation ids it receives."""
    recorded: list[uuid.UUID] = []

    def fake_ingest(raw_payload, correlation_id):
        recorded.append(correlation_id)

    runner._ingest = fake_ingest  # type: ignore[assignment]
    return recorded


class TestCorrelationId:
    def test_deterministic_for_same_inputs(self) -> None:
        run_id = uuid.uuid4()
        snapshot_id = uuid.uuid4()
        assert _correlation_id_for(run_id, snapshot_id) == _correlation_id_for(
            run_id, snapshot_id
        )

    def test_varies_across_snapshots_or_runs(self) -> None:
        run_a, run_b = uuid.uuid4(), uuid.uuid4()
        snapshot_a, snapshot_b = uuid.uuid4(), uuid.uuid4()
        ids = {
            _correlation_id_for(run_a, snapshot_a),
            _correlation_id_for(run_b, snapshot_a),
            _correlation_id_for(run_a, snapshot_b),
        }
        assert len(ids) == 3

    def test_returns_valid_uuid(self) -> None:
        value = _correlation_id_for(uuid.uuid4(), uuid.uuid4())
        assert isinstance(value, uuid.UUID)
        assert uuid.UUID(str(value)) == value


class TestRunnerGuardRails:
    def test_missing_run_returns_missing(self) -> None:
        result = BacktestRunnerService().run(uuid.uuid4())
        assert result["status"] == "MISSING"

    def test_refuses_non_eager_celery(self, backtest_run, settings) -> None:
        settings.CELERY_TASK_ALWAYS_EAGER = False
        result = BacktestRunnerService().run(backtest_run.id)
        assert result["status"] == "FAILED"
        assert "CELERY_TASK_ALWAYS_EAGER" in result["reason"]
        run = BacktestRun.objects.get(id=backtest_run.id)
        assert run.status == BacktestRunStatus.FAILED

    def test_completed_run_is_noop(self, backtest_run) -> None:
        repo = __import__(
            "apps.backtesting.repository", fromlist=["BacktestRunRepository"]
        ).BacktestRunRepository()
        repo.mark_completed(backtest_run.id)
        result = BacktestRunnerService().run(backtest_run.id)
        assert result["status"] == "ALREADY_COMPLETED"

    def test_empty_run_completes_immediately(self, backtest_run) -> None:
        result = BacktestRunnerService().run(backtest_run.id)
        assert result["status"] == "COMPLETED"
        assert result["bars_processed"] == "0"
        run = BacktestRun.objects.get(id=backtest_run.id)
        assert run.status == BacktestRunStatus.COMPLETED
        assert run.completed_at is not None


class TestRunnerReplay:
    def test_processes_snapshots_in_chronological_order(self, backtest_run) -> None:
        t1 = datetime(2024, 6, 10, 5, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 6, 10, 7, 0, 0, tzinfo=timezone.utc)
        t3 = datetime(2024, 6, 10, 9, 0, 0, tzinfo=timezone.utc)
        sid1 = _seed_snapshot("RELIANCE", t2)
        sid2 = _seed_snapshot("RELIANCE", t1)
        sid3 = _seed_snapshot("RELIANCE", t3)

        runner = BacktestRunnerService()
        recorded = _ingest_recorder(runner)
        result = runner.run(backtest_run.id)

        assert result["status"] == "COMPLETED"
        assert result["bars_processed"] == "3"
        expected = [
            _correlation_id_for(backtest_run.id, sid2),
            _correlation_id_for(backtest_run.id, sid1),
            _correlation_id_for(backtest_run.id, sid3),
        ]
        assert recorded == expected
        run = BacktestRun.objects.get(id=backtest_run.id)
        assert run.last_processed_snapshot_id == sid3

    def test_resume_from_cursor_after_failure(self, backtest_run) -> None:
        t1 = datetime(2024, 6, 10, 5, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 6, 10, 7, 0, 0, tzinfo=timezone.utc)
        t3 = datetime(2024, 6, 10, 9, 0, 0, tzinfo=timezone.utc)
        sid1 = _seed_snapshot("RELIANCE", t1)
        sid2 = _seed_snapshot("RELIANCE", t2)
        sid3 = _seed_snapshot("RELIANCE", t3)

        runner = BacktestRunnerService()
        attempts: list[uuid.UUID] = []
        calls = {"n": 0}

        def flaky_ingest(raw_payload, correlation_id):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("broker unavailable")
            attempts.append(correlation_id)

        runner._ingest = flaky_ingest  # type: ignore[assignment]
        first = runner.run(backtest_run.id)

        assert first["status"] == "FAILED"
        run = BacktestRun.objects.get(id=backtest_run.id)
        assert run.status == BacktestRunStatus.FAILED
        assert run.last_processed_snapshot_id == sid1
        assert attempts == [_correlation_id_for(backtest_run.id, sid1)]

        # Resume: only unprocessed bars (t2, t3) replay.
        resume_recorder = _ingest_recorder(runner)
        second = runner.run(backtest_run.id)
        assert second["status"] == "COMPLETED"
        assert second["bars_processed"] == "2"
        assert resume_recorder == [
            _correlation_id_for(backtest_run.id, sid2),
            _correlation_id_for(backtest_run.id, sid3),
        ]

    def test_invalid_payload_marks_run_failed(self, backtest_run) -> None:
        _seed_snapshot("RELIANCE", datetime(2024, 6, 10, 7, 0, 0, tzinfo=timezone.utc),
                       close=None)
        result = BacktestRunnerService().run(backtest_run.id)
        assert result["status"] == "FAILED"
        run = BacktestRun.objects.get(id=backtest_run.id)
        assert run.status == BacktestRunStatus.FAILED
        assert "close" in run.failure_reason or "required" in run.failure_reason


class TestStatsService:
    def test_stats_empty_run(self, backtest_run) -> None:
        from decimal import Decimal

        stats = BacktestStatsService().run_stats(backtest_run)
        assert stats["status"] == "PENDING"
        assert stats["trade_count"] == 0
        assert stats["fill_count"] == 0
        assert Decimal(stats["equity_at_completion"]) == Decimal("1000000")

    def test_stats_reflects_orders_and_capital(self, backtest_run, settings) -> None:
        from decimal import Decimal

        from apps.execution.application.execution_request_service import (
            ExecutionRequestService,
        )
        from apps.execution.infrastructure.tasks import process_order
        from apps.risk_management.domain.events import RiskApproved

        settings.EXECUTION_ENGINE_ENABLED = True

        approved = RiskApproved(
            symbol="RELIANCE",
            rule_id="long_momentum_v1",
            event_type="BREAKOUT",
            entry_price=Decimal("103.00"),
            stop_loss=Decimal("100.00"),
            position_size=500,
            risk_amount=Decimal("10000"),
            risk_pct_of_capital=Decimal("0.01"),
            risk_reward_ratio=Decimal("3.5"),
            portfolio_gateway_impl="portfolio_v1",
        )
        payload = approved.to_payload()
        payload["account_id"] = str(backtest_run.account_id)

        correlation_id = uuid.uuid4()
        result = ExecutionRequestService().intake(
            payload=payload,
            correlation_id=correlation_id,
            causation_id=None,
            risk_approved_event_id=uuid.uuid4(),
        )
        assert result.outcome == "CREATED"
        process_order.delay(str(result.order_id), correlation_id=str(correlation_id))

        stats = BacktestStatsService().run_stats(backtest_run)
        assert stats["trade_count"] == 1
        assert stats["fill_count"] == 1
        assert stats["win_count"] == 0
        assert stats["trades"][0]["symbol"] == "RELIANCE"
        assert stats["trades"][0]["side"] == "LONG"
        assert Decimal(stats["available_capital"]) == Decimal("948500")

    def test_stats_buckets_trades_by_regime(self, backtest_run) -> None:
        from decimal import Decimal

        from apps.execution.infrastructure.models import ExecutionRequest, Order
        from apps.rule_engine.infrastructure.models import RuleExecution

        account_id = backtest_run.account_id

        def _make_order(side, entry, fill, qty, corr, regime):
            req = ExecutionRequest.objects.create(
                idempotency_key=f"key-{uuid.uuid4().hex}",
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
            Order.objects.create(
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
            RuleExecution.objects.create(
                rule_id="long_momentum_v1",
                symbol="RELIANCE",
                severity="medium",
                trigger_data={"regime": regime},
                analysis_event_id=corr,
            )

        bull_corr = uuid.uuid4()
        bear_corr = uuid.uuid4()
        _make_order("LONG", "100.00", "110.00", 100, bull_corr, "BULLISH")
        _make_order("SHORT", "120.00", "125.00", 100, bear_corr, "BEARISH")

        stats = BacktestStatsService().run_stats(backtest_run)
        assert stats["missing_regime_count"] == 0
        assert stats["by_regime"]["BULLISH"]["trade_count"] == 1
        assert stats["by_regime"]["BULLISH"]["win_count"] == 1
        assert stats["by_regime"]["BULLISH"]["loss_count"] == 0
        assert stats["by_regime"]["BULLISH"]["trades"][0]["order_id"] is not None
        assert stats["by_regime"]["BEARISH"]["trade_count"] == 1
        assert stats["by_regime"]["BEARISH"]["win_count"] == 0
        assert stats["by_regime"]["BEARISH"]["loss_count"] == 1
        assert Decimal(stats["by_regime"]["BEARISH"]["gross_loss"]) > Decimal("0")

    def test_stats_counts_missing_regime(self, backtest_run) -> None:
        from decimal import Decimal

        from apps.execution.infrastructure.models import ExecutionRequest, Order

        account_id = backtest_run.account_id
        corr = uuid.uuid4()
        req = ExecutionRequest.objects.create(
            idempotency_key=f"key-{uuid.uuid4().hex}",
            account_id=account_id,
            symbol="RELIANCE",
            side="LONG",
            quantity=Decimal("100"),
            entry_price=Decimal("100.00"),
            stop_loss=Decimal("90.00"),
            correlation_id=corr,
            risk_approved_event_id=uuid.uuid4(),
            rule_id="long_momentum_v1",
            event_type="BREAKOUT",
            status="FILLED",
        )
        Order.objects.create(
            execution_request=req,
            account_id=account_id,
            symbol="RELIANCE",
            side="LONG",
            quantity=Decimal("100"),
            status="FILLED",
            filled_quantity=Decimal("100"),
            avg_fill_price=Decimal("110.00"),
            entry_price=Decimal("100.00"),
            stop_loss=Decimal("90.00"),
            correlation_id=corr,
        )

        stats = BacktestStatsService().run_stats(backtest_run)
        assert stats["missing_regime_count"] == 1
        assert stats["by_regime"] == {}
