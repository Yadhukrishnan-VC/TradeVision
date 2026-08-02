from __future__ import annotations

import uuid
from datetime import datetime, timezone

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
    """Integration tests observe published events via the in-memory bus."""
    from django.conf import settings

    settings.EVENT_BUS_IMPLEMENTATION = "fake"
    reset_event_bus()
    yield
    reset_event_bus()


@pytest.fixture(autouse=True)
def _market_open(monkeypatch) -> None:
    """Deterministic market/freshness state regardless of wall-clock time."""
    from apps.risk_management.gateways.market_calendar_status_gateway import (
        MarketCalendarStatusGateway,
    )

    monkeypatch.setattr(MarketCalendarStatusGateway, "is_market_open", lambda self, dt: True)
    monkeypatch.setattr(MarketCalendarStatusGateway, "is_fresh", lambda self, a, r: True)


def _register_risk_handlers(bus):
    from apps.risk_management.infrastructure.event_handlers import register_handlers

    register_handlers(bus)


def _publish_rule_fired(
    *,
    rule_id: str = "long_momentum_v1",
    symbol: str = "RELIANCE",
    entry_price: str = "103.00",
    stop_loss: str = "101.00",
    target_price: str = "110.00",
    analysis_event_id: uuid.UUID | None = None,
) -> tuple[DomainEvent, uuid.UUID]:
    firing_id = analysis_event_id or uuid.uuid4()
    event = DomainEvent.create(
        event_type="rule_engine.RuleFired",
        payload={
            "symbol": symbol,
            "event_type": "BREAKOUT",
            "rule_id": rule_id,
            "severity": "HIGH",
            "trigger_data": {
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "target_price": target_price,
            },
            "analysis_event_id": str(firing_id),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        },
        correlation_id=firing_id,
    )
    bus = get_event_bus()
    bus.publish(event)
    return event, firing_id


class TestRuleFiredToRiskDecision:
    def test_approved_event_published(self) -> None:
        bus = get_event_bus()
        _register_risk_handlers(bus)

        fired_event, firing_id = _publish_rule_fired()

        approved = next(
            e for e in bus.published_events if e.event_type == "risk_management.RiskApproved"
        )
        assert approved.correlation_id == firing_id
        assert approved.causation_id == fired_event.event_id
        assert approved.payload["position_size"] == 5000
        assert approved.payload["portfolio_gateway_impl"] == "stub"

        execution = RiskDecisionExecution.objects.get(
            analysis_event_id=str(firing_id),
            rule_id="long_momentum_v1",
        )
        assert execution.status == "APPROVED"
        assert execution.portfolio_gateway_impl == "stub"

    def test_rejected_event_published(self) -> None:
        bus = get_event_bus()
        _register_risk_handlers(bus)

        _publish_rule_fired(stop_loss="103.00")

        rejected = next(
            e for e in bus.published_events if e.event_type == "risk_management.RiskRejected"
        )
        assert rejected.payload["reason_code"] == "STOP_EQUALS_ENTRY"
        assert "position_size" not in rejected.payload
        assert rejected.payload["portfolio_gateway_impl"] == "stub"

    def test_duplicate_delivery_is_skipped(self) -> None:
        bus = get_event_bus()
        _register_risk_handlers(bus)

        _, firing_id = _publish_rule_fired()
        # Redeliver the same event (same analysis_event_id -> same idempotency key).
        bus.publish(DomainEvent.create(
            event_type="rule_engine.RuleFired",
            payload={
                "symbol": "RELIANCE",
                "event_type": "BREAKOUT",
                "rule_id": "long_momentum_v1",
                "severity": "HIGH",
                "trigger_data": {
                    "entry_price": "103.00",
                    "stop_loss": "101.00",
                    "target_price": "110.00",
                },
                "analysis_event_id": str(firing_id),
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            },
            correlation_id=firing_id,
        ))

        assert RiskDecisionExecution.objects.filter(
            analysis_event_id=str(firing_id),
            rule_id="long_momentum_v1",
        ).count() == 1
        approved = [
            e for e in bus.published_events if e.event_type == "risk_management.RiskApproved"
        ]
        assert len(approved) == 1

    def test_kill_switch_blocked_by_service(self) -> None:
        from apps.risk_management.application.kill_switch_service import (
            KillSwitchService,
        )

        KillSwitchService().activate(scope="GLOBAL", reason="halt")
        bus = get_event_bus()
        _register_risk_handlers(bus)

        _publish_rule_fired()

        rejected = next(
            e for e in bus.published_events if e.event_type == "risk_management.RiskRejected"
        )
        assert rejected.payload["reason_code"] == "KILL_SWITCH_ACTIVE"


class TestKillSwitchAudit:
    def test_kill_switch_toggle_produces_audit_entry(self) -> None:
        from apps.audit_log.infrastructure.event_handlers import (
            register_handlers as audit_register,
        )
        from apps.audit_log.infrastructure.models import AuditLogEntry

        bus = get_event_bus()
        audit_register(bus)

        from apps.risk_management.application.kill_switch_service import (
            KillSwitchService,
        )

        KillSwitchService().activate(scope="SYMBOL", symbol="RELIANCE", reason="halt")

        assert AuditLogEntry.objects.filter(
            action="risk_management.KillSwitchActivated"
        ).count() == 1
        entry = AuditLogEntry.objects.get(action="risk_management.KillSwitchActivated")
        assert entry.metadata["scope"] == "SYMBOL"
        assert entry.metadata["symbol"] == "RELIANCE"
