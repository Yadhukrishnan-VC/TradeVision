from __future__ import annotations

import uuid
from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _use_fake_event_bus() -> None:
    """Integration tests observe published events via the in-memory bus."""
    from django.conf import settings

    from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus

    settings.EVENT_BUS_IMPLEMENTATION = "fake"
    reset_event_bus()
    yield
    reset_event_bus()


@pytest.fixture(autouse=True)
def _execution_gate_enabled(settings) -> None:
    """Integration tests exercise the activated execution path by default.

    The production default for ``EXECUTION_ENGINE_ENABLED`` is ``False``
    (safety gate). The pre-existing execution integration tests run the full
    RiskApproved -> order chain, so they enable the gate explicitly here.
    Dedicated gate tests override it per-case via ``override_settings``.
    """
    settings.EXECUTION_ENGINE_ENABLED = True


@pytest.fixture(autouse=True)
def _funded_default_account(db, django_user_model):
    """A default account with 1,000,000 in capital (M4 real gateway default)."""
    from apps.accounts.infrastructure.models import Account
    from apps.portfolio.application.capital_service import CapitalService

    user = django_user_model.objects.create_user(
        username=f"exec_user_{uuid.uuid4().hex[:8]}", password="p"
    )
    account = Account.objects.create(name="Primary", owner=user, is_default=True)
    CapitalService().deposit(account.id, Decimal("1000000"))
    return account


@pytest.fixture
def account(_funded_default_account):
    """Public alias for the funded default account."""
    return _funded_default_account


@pytest.fixture(autouse=True)
def _market_open(monkeypatch) -> None:
    """Deterministic market/freshness state regardless of wall-clock time."""
    from apps.risk_management.gateways.market_calendar_status_gateway import (
        MarketCalendarStatusGateway,
    )

    monkeypatch.setattr(MarketCalendarStatusGateway, "is_market_open", lambda self, dt: True)
    monkeypatch.setattr(MarketCalendarStatusGateway, "is_fresh", lambda self, a, r: True)


@pytest.fixture
def register_risk_handlers():
    """Register the risk_management event handlers on the active bus."""

    def _register(bus):
        from apps.risk_management.infrastructure.event_handlers import (
            register_handlers,
        )

        register_handlers(bus)

    return _register


@pytest.fixture
def register_dashboard_handlers():
    """Register the dashboard trading-core consumers on the active bus."""

    def _register(bus):
        from apps.dashboard.infrastructure.trading_core.event_consumers import (
            register_handlers as register_dashboard,
        )

        register_dashboard(bus)

    return _register
