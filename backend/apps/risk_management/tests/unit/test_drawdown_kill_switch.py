from __future__ import annotations

from decimal import Decimal

import pytest

from apps.risk_management.application.kill_switch_service import KillSwitchService
from apps.risk_management.application.risk_config import RiskConfig
from apps.risk_management.domain.value_objects import RejectionReason
from apps.risk_management.infrastructure.models import KillSwitchState
from apps.risk_management.tests.unit.helpers import (
    FakeCapitalGateway,
    FakeMarketGateway,
    FakePortfolioGateway,
    build_service,
    make_payload,
)


@pytest.mark.django_db
class TestDrawdownKillSwitch:
    def test_daily_breach_trips_account_scope(self) -> None:
        service = KillSwitchService()
        state = service.evaluate_drawdown_limits(
            daily_loss=Decimal("20000"),
            weekly_loss=Decimal("20000"),
            capital=Decimal("100000"),
            max_daily_loss_pct=Decimal("0.15"),
        )
        assert state is not None
        assert state.scope == "ACCOUNT"
        assert state.is_active is True
        assert "daily" in state.reason
        assert "20000" in state.reason  # values at trip time recorded
        assert "0.15" in state.reason

    def test_weekly_breach_trips_account_scope(self) -> None:
        service = KillSwitchService()
        state = service.evaluate_drawdown_limits(
            daily_loss=Decimal("0"),
            weekly_loss=Decimal("30000"),
            capital=Decimal("100000"),
            max_weekly_loss_pct=Decimal("0.25"),
        )
        assert state is not None
        assert state.scope == "ACCOUNT"
        assert "weekly" in state.reason

    def test_no_trip_within_limits(self) -> None:
        service = KillSwitchService()
        state = service.evaluate_drawdown_limits(
            daily_loss=Decimal("1000"),
            weekly_loss=Decimal("1000"),
            capital=Decimal("100000"),
            max_daily_loss_pct=Decimal("0.15"),
            max_weekly_loss_pct=Decimal("0.25"),
        )
        assert state is None

    def test_no_thresholds_configured_never_trips(self) -> None:
        service = KillSwitchService()
        state = service.evaluate_drawdown_limits(
            daily_loss=Decimal("20000"),
            weekly_loss=Decimal("0"),
            capital=Decimal("100000"),
        )
        assert state is None

    def test_non_positive_capital_never_trips(self) -> None:
        service = KillSwitchService()
        state = service.evaluate_drawdown_limits(
            daily_loss=Decimal("20000"),
            weekly_loss=Decimal("0"),
            capital=Decimal("0"),
            max_daily_loss_pct=Decimal("0.15"),
        )
        assert state is None

    def test_idempotent_when_account_already_active(self) -> None:
        service = KillSwitchService()
        first = service.evaluate_drawdown_limits(
            daily_loss=Decimal("20000"),
            weekly_loss=Decimal("0"),
            capital=Decimal("100000"),
            max_daily_loss_pct=Decimal("0.15"),
        )
        second = service.evaluate_drawdown_limits(
            daily_loss=Decimal("20000"),
            weekly_loss=Decimal("0"),
            capital=Decimal("100000"),
            max_daily_loss_pct=Decimal("0.15"),
        )
        assert first is not None and second is not None
        assert first.id == second.id
        assert KillSwitchState.objects.filter(scope="ACCOUNT", is_active=True).count() == 1

    def test_daily_breach_blocks_trades_in_same_session(self) -> None:
        """A daily-limit breach must trip the switch BEFORE further capital is
        placed at risk within the same session: a subsequent rule firing is
        rejected with KILL_SWITCH_ACTIVE."""
        service = KillSwitchService()
        service.evaluate_drawdown_limits(
            daily_loss=Decimal("20000"),
            weekly_loss=Decimal("0"),
            capital=Decimal("100000"),
            max_daily_loss_pct=Decimal("0.15"),
        )

        capital = FakeCapitalGateway(available_capital=Decimal("100000"))
        portfolio = FakePortfolioGateway()
        market = FakeMarketGateway()
        evaluation = build_service(
            config=RiskConfig(),
            capital=capital,
            portfolio=portfolio,
            market=market,
            kill_switch=service,
        )
        decision = evaluation.evaluate_rule_firing(make_payload())
        assert decision.status.value == "REJECTED"
        assert decision.rejection.code is RejectionReason.KILL_SWITCH_ACTIVE

    def test_drawdown_limits_within_session_allow_flow(self) -> None:
        """Before a breach, the same session still approves trades."""
        service = KillSwitchService()
        service.evaluate_drawdown_limits(
            daily_loss=Decimal("1000"),
            weekly_loss=Decimal("0"),
            capital=Decimal("100000"),
            max_daily_loss_pct=Decimal("0.15"),
        )
        assert service.is_trade_blocked("RELIANCE") is False

        capital = FakeCapitalGateway(available_capital=Decimal("100000"))
        portfolio = FakePortfolioGateway()
        market = FakeMarketGateway()
        evaluation = build_service(
            config=RiskConfig(),
            capital=capital,
            portfolio=portfolio,
            market=market,
            kill_switch=service,
        )
        decision = evaluation.evaluate_rule_firing(make_payload())
        assert decision.status.value == "APPROVED"