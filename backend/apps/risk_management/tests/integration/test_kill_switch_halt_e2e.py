"""ADR-030 §5.3 gate — end-to-end kill-switch halt proofs.

Not unit tests of the flag: each test triggers the kill switch through one of
the two operator-reachable surfaces (REST API, out-of-band management
command), then pushes a fresh ``rule_engine.RuleFired`` through the real
event chain (bus -> evaluate_rule_firing -> risk checks) and asserts that a
subsequent order attempt is REJECTED with ``KILL_SWITCH_ACTIVE`` — i.e.
trading actually halts, not just that a boolean flips.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from apps.accounts.application.services import APIKeyService
from apps.accounts.domain.value_objects import Scope
from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import (
    get_event_bus,
    reset_event_bus,
)
from apps.risk_management.infrastructure.models import (
    KillSwitchState,
    RiskDecisionExecution,
)
from rest_framework import status
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

KILL_SWITCH_ACTIVATE_PATH = "/api/v1/risk-management/kill-switch/activate/"
KILL_SWITCH_DEACTIVATE_PATH = "/api/v1/risk-management/kill-switch/deactivate/"


@pytest.fixture(autouse=True)
def _use_fake_event_bus() -> None:
    """Integration tests observe published events via the in-memory bus."""
    from django.conf import settings

    settings.EVENT_BUS_IMPLEMENTATION = "fake"
    reset_event_bus()
    yield
    reset_event_bus()


@pytest.fixture(autouse=True)
def _funded_default_account(db, django_user_model):
    """Default account with 1,000,000 in capital (production portfolio gateway)."""
    from apps.accounts.infrastructure.models import Account
    from apps.portfolio.application.capital_service import CapitalService

    user = django_user_model.objects.create_user(
        username=f"halt_user_{uuid.uuid4().hex[:8]}", password="p"
    )
    account = Account.objects.create(name="Primary", owner=user, is_default=True)
    CapitalService().deposit(account.id, Decimal(1000000))
    return account


@pytest.fixture(autouse=True)
def _market_open(monkeypatch) -> None:
    """Deterministic market/freshness state regardless of wall-clock time."""
    from apps.risk_management.gateways.market_calendar_status_gateway import (
        MarketCalendarStatusGateway,
    )

    monkeypatch.setattr(
        MarketCalendarStatusGateway, "is_market_open", lambda self, dt: True
    )
    monkeypatch.setattr(
        MarketCalendarStatusGateway, "is_fresh", lambda self, a, r: True
    )


def _register_risk_handlers(bus) -> None:
    from apps.risk_management.infrastructure.event_handlers import register_handlers

    register_handlers(bus)


def _fire_rule(symbol: str = "RELIANCE") -> None:
    """Push one order attempt's trigger through the real risk chain."""
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


def _published(bus, event_type: str) -> list[DomainEvent]:
    return [e for e in bus.published_events if e.event_type == event_type]


def _scoped_client(api_client: APIClient, user: Any) -> APIClient:
    api_key, _ = APIKeyService().create_key(user, [Scope.MANAGE_RISK_POLICY])
    api_client.force_authenticate(user=user, token=api_key)
    return api_client


class TestKillSwitchHaltsViaApiPath:
    def test_activated_scope_rejects_subsequent_order_attempt(
        self, api_client: APIClient, user: Any
    ) -> None:
        client = _scoped_client(api_client, user)
        response = client.post(
            KILL_SWITCH_ACTIVATE_PATH,
            {"scope": "GLOBAL", "reason": "phase2 gate drill (API path)"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

        bus = get_event_bus()
        _register_risk_handlers(bus)

        _fire_rule()

        rejected = _published(bus, "risk_management.RiskRejected")
        assert len(rejected) == 1
        assert rejected[0].payload["reason_code"] == "KILL_SWITCH_ACTIVE"
        approved = _published(bus, "risk_management.RiskApproved")
        assert approved == []
        decision = RiskDecisionExecution.objects.get(status="REJECTED")
        assert decision.rejection_code == "KILL_SWITCH_ACTIVE"

    def test_deactivate_restores_order_flow(
        self, api_client: APIClient, user: Any
    ) -> None:
        client = _scoped_client(api_client, user)
        client.post(KILL_SWITCH_ACTIVATE_PATH, {"scope": "GLOBAL"}, format="json")

        bus = get_event_bus()
        _register_risk_handlers(bus)

        response = client.post(
            KILL_SWITCH_DEACTIVATE_PATH,
            {"scope": "GLOBAL", "reason": "drill over"},
            format="json",
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT

        _fire_rule()

        approved = _published(bus, "risk_management.RiskApproved")
        rejected = _published(bus, "risk_management.RiskRejected")
        assert len(approved) == 1
        assert rejected == []


class TestKillSwitchHaltsViaManagementCommand:
    def test_out_of_band_activation_blocks_subsequent_order_attempt(self) -> None:
        from django.core.management import call_command

        call_command(
            "kill_switch",
            "--activate",
            "--scope",
            "GLOBAL",
            "--reason",
            "adapter misbehaving (out-of-band drill)",
        )
        assert KillSwitchState.objects.filter(scope="GLOBAL", is_active=True).exists()

        bus = get_event_bus()
        _register_risk_handlers(bus)

        _fire_rule()

        rejected = _published(bus, "risk_management.RiskRejected")
        assert len(rejected) == 1
        assert rejected[0].payload["reason_code"] == "KILL_SWITCH_ACTIVE"

    def test_out_of_band_symbol_scope_blocks_only_that_symbol(self) -> None:
        from django.core.management import call_command

        call_command(
            "kill_switch",
            "--activate",
            "--scope",
            "SYMBOL",
            "--symbol",
            "RELIANCE",
            "--reason",
            "bad ticks on RELIANCE",
        )

        bus = get_event_bus()
        _register_risk_handlers(bus)

        _fire_rule(symbol="TCS")  # different symbol must keep flowing

        approved = _published(bus, "risk_management.RiskApproved")
        assert len(approved) == 1
        assert approved[0].payload["symbol"] == "TCS"

    def test_out_of_band_deactivate_restores_order_flow(self) -> None:
        from django.core.management import call_command

        call_command(
            "kill_switch", "--activate", "--scope", "GLOBAL", "--reason", "halt"
        )
        call_command(
            "kill_switch", "--deactivate", "--scope", "GLOBAL", "--reason", "closed"
        )

        bus = get_event_bus()
        _register_risk_handlers(bus)

        _fire_rule()

        assert len(_published(bus, "risk_management.RiskApproved")) == 1

    def test_status_lists_active_scopes(self, capsys) -> None:
        from django.core.management import call_command

        call_command(
            "kill_switch", "--activate", "--scope", "GLOBAL", "--reason", "halt"
        )

        call_command("kill_switch", "--status")

        out = capsys.readouterr().out
        assert "ACTIVE scope=GLOBAL" in out
