"""ADR-030 §5.2 gate — hard-capped max order size and max daily loss.

Proves the configured caps are *enforced* by the real risk chain, not just
present in settings:

- maximum order size: an approved order's ``position_size`` is clamped to
  ``RISK_MANAGEMENT["max_position_size"]`` no matter how large the raw
  sizing wants to be — no approved order can exceed the cap;
- maximum daily loss: once the day's realized loss reaches
  ``RISK_MANAGEMENT["daily_loss_limit"]``, every subsequent evaluation is
  REJECTED with ``DAILY_LOSS_LIMIT_EXCEEDED``.

Both run through the production path: bus -> evaluate_rule_firing ->
RiskEvaluationService -> portfolio gateway -> persisted decision + event.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import (
    get_event_bus,
    reset_event_bus,
)
from apps.risk_management.infrastructure.models import RiskDecisionExecution

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _use_fake_event_bus() -> None:
    from django.conf import settings

    settings.EVENT_BUS_IMPLEMENTATION = "fake"
    reset_event_bus()
    yield
    reset_event_bus()


@pytest.fixture(autouse=True)
def _funded_default_account(db, django_user_model):
    from apps.accounts.infrastructure.models import Account
    from apps.portfolio.application.capital_service import CapitalService

    user = django_user_model.objects.create_user(
        username=f"cap_user_{uuid.uuid4().hex[:8]}", password="p"
    )
    account = Account.objects.create(name="Primary", owner=user, is_default=True)
    CapitalService().deposit(account.id, Decimal(1000000))
    return account


@pytest.fixture(autouse=True)
def _market_open(monkeypatch) -> None:
    from apps.risk_management.gateways.market_calendar_status_gateway import (
        MarketCalendarStatusGateway,
    )

    monkeypatch.setattr(
        MarketCalendarStatusGateway, "is_market_open", lambda self, dt: True
    )
    monkeypatch.setattr(
        MarketCalendarStatusGateway, "is_fresh", lambda self, a, r: True
    )


def _caps_settings(**overrides) -> dict:
    """Minimal RISK_MANAGEMENT dict with the two Phase-2 gate caps."""
    return {
        "risk_pct": Decimal("0.01"),
        "max_position_size": overrides.get("max_position_size", 1_000_000),
        "max_exposure_cap": Decimal(1000000),
        "daily_loss_limit": overrides.get("daily_loss_limit"),
        "min_risk_reward": Decimal("1.0"),
        "kill_switch_active": False,
        "tradable_symbols": [],
        "max_freshness_seconds": 600,
        "market_hours_only": True,
    }


def _fire_rule(symbol: str = "RELIANCE") -> None:
    """One order attempt: entry 103 / stop 101 => raw sizing 5000 @ capital 1M."""
    event = DomainEvent.create(
        event_type="rule_engine.RuleFired",
        payload={
            "symbol": symbol,
            "event_type": "BREAKOUT",
            "rule_id": "long_momentum_v1",
            "severity": "HIGH",
            "trigger_data": {
                "entry_price": "103.00",
                "stop_loss": "101.00",
                "target_price": "110.00",
            },
            "analysis_event_id": str(uuid.uuid4()),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        },
        correlation_id=uuid.uuid4(),
    )
    get_event_bus().publish(event)


class TestMaxOrderSizeCap:
    def test_approved_order_is_clamped_to_configured_cap(self, settings) -> None:
        # Raw sizing at capital 1M / risk 1% / |103-101| = 5000 shares; the cap
        # must clamp the approved order to 10 — never above.
        settings.RISK_MANAGEMENT = _caps_settings(max_position_size=10)

        bus = get_event_bus()
        from apps.risk_management.infrastructure.event_handlers import register_handlers

        register_handlers(bus)

        _fire_rule()

        approved = [
            e
            for e in bus.published_events
            if e.event_type == "risk_management.RiskApproved"
        ]
        assert len(approved) == 1
        assert approved[0].payload["position_size"] == 10
        assert approved[0].payload["position_size"] <= 10

    def test_cap_below_one_rejects_instead_of_approving(self, settings) -> None:
        settings.RISK_MANAGEMENT = _caps_settings(max_position_size=0)

        bus = get_event_bus()
        from apps.risk_management.infrastructure.event_handlers import register_handlers

        register_handlers(bus)

        _fire_rule()

        rejected = [
            e
            for e in bus.published_events
            if e.event_type == "risk_management.RiskRejected"
        ]
        assert len(rejected) == 1
        assert rejected[0].payload["reason_code"] == "POSITION_SIZE_ZERO"


class TestMaxDailyLossCap:
    def test_daily_loss_breach_rejects_subsequent_order(self, settings) -> None:
        from apps.portfolio.application.capital_service import CapitalService

        settings.RISK_MANAGEMENT = _caps_settings(daily_loss_limit=Decimal(150))

        bus = get_event_bus()
        from apps.risk_management.infrastructure.event_handlers import register_handlers

        register_handlers(bus)

        # Realized -200 on the ledger through the real capital service; the
        # portfolio gateway reports magnitude 200 >= limit 150.
        from apps.accounts.infrastructure.models import Account

        account_id = Account.objects.get(is_default=True).id
        CapitalService().record_realized_pnl(account_id, Decimal(-200))

        _fire_rule()

        rejected = [
            e
            for e in bus.published_events
            if e.event_type == "risk_management.RiskRejected"
        ]
        assert len(rejected) == 1
        assert rejected[0].payload["reason_code"] == "DAILY_LOSS_LIMIT_EXCEEDED"
        decision = RiskDecisionExecution.objects.get(status="REJECTED")
        assert decision.rejection_code == "DAILY_LOSS_LIMIT_EXCEEDED"

    def test_loss_under_limit_still_approves(self, settings) -> None:
        from apps.accounts.infrastructure.models import Account
        from apps.portfolio.application.capital_service import CapitalService

        settings.RISK_MANAGEMENT = _caps_settings(daily_loss_limit=Decimal(150))

        bus = get_event_bus()
        from apps.risk_management.infrastructure.event_handlers import register_handlers

        register_handlers(bus)

        CapitalService().record_realized_pnl(
            Account.objects.get(is_default=True).id, Decimal(-100)
        )

        _fire_rule()

        approved = [
            e
            for e in bus.published_events
            if e.event_type == "risk_management.RiskApproved"
        ]
        assert len(approved) == 1
