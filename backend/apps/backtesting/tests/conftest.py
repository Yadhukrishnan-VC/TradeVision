"""Batch M3 — Backtest replay test fixtures.

Every backtest test needs a deterministic event bus (the singleton
``get_event_bus()`` reset per test), the execution gate enabled, and a
funded, isolated account for the run. The pipeline tests additionally seed
the ``market_data`` rows that the intelligence session-facts enrichment
reads (opening 15-minute candle + trailing daily candles) and register the
real event handlers for the full replay chain.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

_IST = ZoneInfo("Asia/Kolkata")

# 2024-06-10 07:00 UTC == 12:30 IST, a Monday inside NSE market hours.
HISTORICAL_BAR_TIME = datetime(2024, 6, 10, 7, 0, 0, tzinfo=timezone.utc)

_TA_PAYLOAD = {
    "ticker": "RELIANCE",
    "exchange": "NSE",
    "timeframe": "1D",
    "close": "103.00",
    "open": "100.00",
    "high": "104.00",
    "low": "99.00",
    "volume": 1_000_000,
    "vwap": "101.50",
    "ema_20": "102.00",
    "pine_id": "long_momentum@tv",
    "pine_version": "5",
}


def _make_ta_payload(**overrides: object) -> dict:
    payload = dict(_TA_PAYLOAD)
    payload.update(overrides)
    return payload


@pytest.fixture(autouse=True)
def _use_fake_event_bus() -> None:
    """Observe published events via the in-memory bus."""
    from django.conf import settings

    from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus

    settings.EVENT_BUS_IMPLEMENTATION = "fake"
    reset_event_bus()
    yield
    reset_event_bus()


@pytest.fixture(autouse=True)
def _execution_gate_enabled(settings) -> None:
    """Backtest replay must exercise the activated execution path."""
    settings.EXECUTION_ENGINE_ENABLED = True


@pytest.fixture
def funded_account(db, django_user_model):
    """A dedicated, funded account for a backtest run (not ``is_default``)."""
    from apps.accounts.infrastructure.models import Account
    from apps.portfolio.application.capital_service import CapitalService

    user = django_user_model.objects.create_user(
        username=f"bt_user_{uuid.uuid4().hex[:8]}", password="p"
    )
    account = Account.objects.create(
        name=f"Backtest {user.username}", owner=user, is_default=False
    )
    CapitalService().deposit(account.id, Decimal("1000000"))
    return account


@pytest.fixture
def default_account(db, django_user_model):
    """A production-style default account, untouched by backtest replay."""
    from apps.accounts.infrastructure.models import Account
    from apps.portfolio.application.capital_service import CapitalService

    user = django_user_model.objects.create_user(
        username=f"prod_{uuid.uuid4().hex[:8]}", password="p"
    )
    account = Account.objects.create(name="Primary", owner=user, is_default=True)
    CapitalService().deposit(account.id, Decimal("1000000"))
    return account


@pytest.fixture
def backtest_run(funded_account):
    """A PENDING ``BacktestRun`` bound to ``funded_account``."""
    from apps.backtesting.models import BacktestRun

    run = BacktestRun(
        symbol="RELIANCE",
        timeframe="1D",
        range_start=datetime(2024, 6, 9, tzinfo=timezone.utc),
        range_end=datetime(2024, 6, 11, tzinfo=timezone.utc),
        account=funded_account,
        status="PENDING",
    )
    run.full_clean()
    run.save()
    return run


@pytest.fixture
def historical_snapshot(db):
    """A historical ``TASnapshot`` row whose payload fires LongMomentumRule.

    ``snapshot_timestamp`` is pinned to the historical bar time so the
    simulation clock freezes at 12:30 IST on a trading day.
    """
    from apps.technical_analysis.infrastructure.models import TASnapshot

    snapshot = TASnapshot(
        symbol="RELIANCE",
        exchange="NSE",
        timeframe="1D",
        pine_id="long_momentum@tv",
        pine_version="5",
        indicators={"vwap": "101.50", "ema_20": "102.00"},
        raw_payload=_make_ta_payload(),
        snapshot_timestamp=HISTORICAL_BAR_TIME,
    )
    snapshot.save()
    return snapshot


@pytest.fixture
def seed_session_facts(monkeypatch, db):
    """Seed the market_data rows the intelligence enrichment reads.

    Creates the RELIANCE Instrument, the current session's opening
    15-minute candle (09:15 IST, Open = Low) and 10 trailing ``1D`` candles
    with modest volume, and patches the market calendar so the current day
    always counts as a trading day (deterministic regardless of wall clock).
    """
    from apps.market_data.infrastructure.models import Candle, Instrument
    from core.market_calendar import MarketCalendar

    monkeypatch.setattr(MarketCalendar, "is_trading_day", lambda self, day: True)

    Instrument.objects.create(
        instrument_token=1002,
        exchange="NSE",
        tradingsymbol="RELIANCE",
        name="Reliance Industries Ltd (Backtest)",
        segment="EQUITY",
        lot_size=1,
        tick_size=Decimal("0.05"),
        instrument_type="EQ",
    )

    session_day = datetime.now(timezone.utc).astimezone(_IST).date()
    opening_utc = datetime.combine(
        session_day, time(9, 15), tzinfo=_IST
    ).astimezone(timezone.utc)
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

    for day_offset in range(1, 11):
        day = session_day - timedelta(days=day_offset)
        day_start = datetime.combine(day, time(0, 0), tzinfo=_IST).astimezone(
            timezone.utc
        )
        Candle.objects.create(
            instrument_id=1002,
            timeframe="1D",
            timestamp=day_start,
            open=Decimal("100.00"),
            high=Decimal("101.00"),
            low=Decimal("99.00"),
            close=Decimal("100.50"),
            volume=100_000,
        )
    return None


@pytest.fixture
def register_all_handlers():
    """Register intelligence + rule_engine + risk_management on the bus."""

    def _register(bus):
        from apps.intelligence.infrastructure.event_handlers import (
            register_handlers as register_intelligence,
        )
        from apps.risk_management.infrastructure.event_handlers import (
            register_handlers as register_risk,
        )
        from apps.rule_engine.infrastructure.event_handlers import (
            register_handlers as register_rule_engine,
        )

        register_intelligence(bus)
        register_rule_engine(bus)
        register_risk(bus)

    return _register


@pytest.fixture
def active_bus(_use_fake_event_bus):
    from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

    return get_event_bus()


__all__ = [
    "HISTORICAL_BAR_TIME",
    "_make_ta_payload",
]
