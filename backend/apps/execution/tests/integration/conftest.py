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
    CapitalService().deposit(account.id, Decimal(1000000))
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


@pytest.fixture
def register_intelligence_handlers():
    """Register the intelligence event handlers on the active bus."""

    def _register(bus):
        from apps.intelligence.infrastructure.event_handlers import (
            register_handlers,
        )

        register_handlers(bus)

    return _register


@pytest.fixture
def register_rule_engine_handlers():
    """Register the rule_engine event handlers on the active bus."""

    def _register(bus):
        from apps.rule_engine.infrastructure.event_handlers import (
            register_handlers,
        )

        register_handlers(bus)

    return _register


@pytest.fixture
def seed_session_facts(monkeypatch):
    """Seed the market_data rows the intelligence enrichment reads.

    SessionFactsService fills the packet's ``opening_15m_*`` fields from
    persisted candles, so this fixture creates a test-local Instrument and
    the session's opening 15-minute candle (09:15 IST). The market calendar
    is patched so the current day always counts as a trading day, keeping
    the enrichment deterministic regardless of wall-clock time.
    """

    from datetime import datetime, time, timezone
    from decimal import Decimal
    from zoneinfo import ZoneInfo

    from apps.market_data.infrastructure.models import Candle, Instrument
    from core.market_calendar import MarketCalendar

    _IST = ZoneInfo("Asia/Kolkata")
    monkeypatch.setattr(MarketCalendar, "is_trading_day", lambda self, day: True)

    session_day = datetime.now(timezone.utc).astimezone(_IST).date()
    opening_utc = datetime.combine(
        session_day, time(9, 15), tzinfo=_IST
    ).astimezone(timezone.utc)

    Instrument.objects.create(
        instrument_token=1002,
        exchange="NSE",
        tradingsymbol="RELIANCE",
        name="Reliance Industries Ltd (E2E)",
        segment="EQUITY",
        lot_size=1,
        tick_size=Decimal("0.05"),
        instrument_type="EQ",
    )
    Candle.objects.create(
        instrument_id=1002,
        timeframe="15min",
        timestamp=opening_utc,
        open=Decimal("100.00"),
        high=Decimal("101.00"),
        low=Decimal("100.00"),
        close=Decimal("100.50"),
        volume=500_000,
    )
