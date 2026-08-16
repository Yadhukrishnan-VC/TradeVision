"""ADR-029 — RuleValidationService verdict computation tests.

Covers the threshold branches (INSUFFICIENT_DATA / GO / NO_GO), the UNKNOWN
regime short-circuit, verdict persistence into ``RuleConfig.validated_regimes``
(including fail-closed ``enabled=False`` on first creation), and the requirement
that only COMPLETED runs are validated.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from apps.backtesting.application.rule_validation_service import (
    MIN_TRADE_COUNT,
    VERDICT_GO,
    VERDICT_INSUFFICIENT_DATA,
    VERDICT_NO_GO,
    RuleValidationService,
)
from apps.backtesting.models import BacktestRun, BacktestRunStatus
from apps.rule_engine.infrastructure.models import RuleConfig

pytestmark = pytest.mark.django_db


def _create_completed_run(funded_account, commission_rate="0.0003", slippage_bps="5.0"):
    run = BacktestRun(
        symbol="RELIANCE",
        timeframe="1D",
        range_start=datetime(2024, 6, 9, tzinfo=timezone.utc),
        range_end=datetime(2024, 6, 11, tzinfo=timezone.utc),
        account=funded_account,
        status=BacktestRunStatus.COMPLETED,
        commission_rate=Decimal(commission_rate),
        slippage_bps=Decimal(slippage_bps),
    )
    run.full_clean()
    run.save()
    return run


def _make_order(account_id, corr, side, entry, fill, qty):
    from apps.execution.infrastructure.models import ExecutionRequest, Fill, Order

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
        rule_id="price_movement_v1",
        event_type="PRICE_MOVEMENT",
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
    Fill.objects.create(
        order=order,
        sequence=0,
        quantity=Decimal(qty),
        price=Decimal(fill),
        occurred_at=datetime(2024, 6, 10, tzinfo=timezone.utc),
    )
    return order


def _make_execution(corr, rule_id="price_movement_v1", regime="BULLISH"):
    from apps.rule_engine.infrastructure.models import RuleExecution

    return RuleExecution.objects.create(
        rule_id=rule_id,
        symbol="RELIANCE",
        severity="medium",
        trigger_data={"regime": regime},
        analysis_event_id=corr,
    )


class TestValidateRunPreconditions:
    def test_rejects_non_completed_run(self, backtest_run) -> None:
        assert backtest_run.status == BacktestRunStatus.PENDING
        with pytest.raises(ValueError):
            RuleValidationService().validate_run(backtest_run)


class TestThresholdBranches:
    def test_insufficient_data_when_below_min_trade_count(
        self, funded_account
    ) -> None:
        run = _create_completed_run(funded_account)
        for i in range(MIN_TRADE_COUNT - 1):
            corr = uuid.uuid4()
            _make_order(run.account_id, corr, "LONG", "100.00", "105.00", "100")
            _make_execution(corr)

        summary = RuleValidationService().validate_run(run)
        assert summary == {"price_movement_v1": {"BULLISH": VERDICT_INSUFFICIENT_DATA}}

        config = RuleConfig.objects.get(rule_id="price_movement_v1")
        assert config.enabled is False
        assert config.validated_regimes["BULLISH"]["status"] == VERDICT_INSUFFICIENT_DATA
        assert config.validated_regimes["BULLISH"]["trade_count"] == MIN_TRADE_COUNT - 1
        assert config.validated_regimes["BULLISH"]["backtest_run_id"] == str(run.id)
        assert "evaluated_at" in config.validated_regimes["BULLISH"]

    def test_go_when_all_metrics_pass(self, funded_account) -> None:
        run = _create_completed_run(funded_account)
        for i in range(MIN_TRADE_COUNT):
            corr = uuid.uuid4()
            _make_order(run.account_id, corr, "LONG", "100.00", "120.00", "100")
            _make_execution(corr)

        summary = RuleValidationService().validate_run(run)
        assert summary == {"price_movement_v1": {"BULLISH": VERDICT_GO}}

        config = RuleConfig.objects.get(rule_id="price_movement_v1")
        verdict = config.validated_regimes["BULLISH"]
        assert verdict["status"] == VERDICT_GO
        assert verdict["trade_count"] == MIN_TRADE_COUNT

    def test_no_go_when_expectancy_negative(self, funded_account) -> None:
        run = _create_completed_run(funded_account)
        for i in range(MIN_TRADE_COUNT):
            corr = uuid.uuid4()
            _make_order(run.account_id, corr, "LONG", "100.00", "98.00", "100")
            _make_execution(corr)

        summary = RuleValidationService().validate_run(run)
        assert summary == {"price_movement_v1": {"BULLISH": VERDICT_NO_GO}}

    def test_no_go_when_max_drawdown_exceeds_threshold(self, funded_account) -> None:
        run = _create_completed_run(funded_account)
        # Alternating deep losers then winners: high drawdown, still >= 30 trades.
        for i in range(MIN_TRADE_COUNT):
            corr = uuid.uuid4()
            entry = "100.00" if i % 2 == 0 else "120.00"
            fill = "50.00" if i % 2 == 0 else "130.00"
            _make_order(run.account_id, corr, "LONG", entry, fill, "100")
            _make_execution(corr)

        summary = RuleValidationService().validate_run(run)
        assert summary == {"price_movement_v1": {"BULLISH": VERDICT_NO_GO}}

    def test_unknown_regime_is_always_no_go(self, funded_account) -> None:
        run = _create_completed_run(funded_account)
        for i in range(MIN_TRADE_COUNT):
            corr = uuid.uuid4()
            _make_order(run.account_id, corr, "LONG", "100.00", "120.00", "100")
            _make_execution(corr, regime=None)

        summary = RuleValidationService().validate_run(run)
        assert summary == {"price_movement_v1": {"UNKNOWN": VERDICT_NO_GO}}

    def test_no_fills_produces_no_verdicts(self, funded_account) -> None:
        run = _create_completed_run(funded_account)
        summary = RuleValidationService().validate_run(run)
        assert summary == {}
        assert RuleConfig.objects.count() == 0


class TestVerdictPersistence:
    def test_creates_config_fail_closed_then_updates(self, funded_account) -> None:
        run = _create_completed_run(funded_account)
        for i in range(MIN_TRADE_COUNT):
            corr = uuid.uuid4()
            _make_order(run.account_id, corr, "LONG", "100.00", "120.00", "100")
            _make_execution(corr)

        assert RuleConfig.objects.count() == 0
        RuleValidationService().validate_run(run)

        config = RuleConfig.objects.get(rule_id="price_movement_v1")
        assert config.enabled is False
        assert config.validated_regimes["BULLISH"]["status"] == VERDICT_GO

    def test_existing_enabled_config_is_never_flipped(self, funded_account) -> None:
        from apps.rule_engine.infrastructure.repositories import RuleConfigRepository

        run = _create_completed_run(funded_account)
        for i in range(MIN_TRADE_COUNT):
            corr = uuid.uuid4()
            _make_order(run.account_id, corr, "LONG", "100.00", "120.00", "100")
            _make_execution(corr)

        RuleConfigRepository().create(
            RuleConfig(rule_id="price_movement_v1", enabled=True)
        )
        RuleValidationService().validate_run(run)

        config = RuleConfig.objects.get(rule_id="price_movement_v1")
        assert config.enabled is True