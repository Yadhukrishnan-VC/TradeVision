"""Research Integrity Suite — adversarial dataset fixtures.

Self-contained: this suite intentionally does NOT import the backtesting
app's test conftest so the adversarial datasets stay independent of the
pipeline's own fixtures. It replays synthetic historical bars through the
REAL event chain (TechnicalAnalysisIngestionService -> EventBus ->
intelligence -> rule_engine -> risk_management -> execution -> PaperBroker)
so a bias introduced anywhere in the chain fails a test.

The deterministic signal used throughout is the same one the M3 pipeline
uses: a ``long_momentum@tv`` bar with ``ema_20`` > ``vwap`` fires
LongMomentumRule; the risk layer approves it (stop loss present) and defers
the fill to the next bar's open.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

_IST = ZoneInfo("Asia/Kolkata")

BASE = datetime(2024, 6, 9, tzinfo=timezone.utc)
RUN_START = BASE
RUN_END = datetime(2024, 6, 14, tzinfo=timezone.utc)

_BAR_TEMPLATE = {
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


def make_ta_payload(**overrides: object) -> dict:
    """A bar payload that deterministically fires LongMomentumRule.

    ``ema_20`` must exceed ``vwap`` for the long-momentum signal; the default
    template already satisfies that. Override ``open``/``close`` etc. per bar.
    """
    payload = dict(_BAR_TEMPLATE)
    payload.update(overrides)
    return payload


def make_run(capital: str = "1000000", **overrides: object):
    """A PENDING BacktestRun bound to an isolated funded account."""
    from django.contrib.auth import get_user_model

    from apps.accounts.infrastructure.models import Account
    from apps.backtesting.models import BacktestRun
    from apps.portfolio.application.capital_service import CapitalService

    user = get_user_model().objects.create_user(
        username=f"ri_user_{uuid.uuid4().hex[:8]}", password="p"
    )

    account = Account.objects.create(
        name=f"ResearchIntegrity {user.username}", owner=user, is_default=False
    )
    CapitalService().deposit(account.id, Decimal(capital))

    run = BacktestRun(
        symbol="RELIANCE",
        timeframe="1D",
        range_start=overrides.pop("range_start", RUN_START),
        range_end=overrides.pop("range_end", RUN_END),
        account=account,
        status="PENDING",
        **overrides,
    )
    run.full_clean()
    run.save()
    return run


def seed_bar(
    timestamp: datetime,
    *,
    open_price: str | None = "100.00",
    close_price: str = "103.00",
    payload_overrides: dict | None = None,
) -> None:
    """Seed one historical TASnapshot bar at ``timestamp``.

    ``open_price=None`` builds a bar with NO ``open`` field — used by the
    look-ahead test to prove the runner fails safe instead of falling back to
    this bar's close (a price not yet known at the open).
    """
    from apps.technical_analysis.infrastructure.models import TASnapshot

    overrides: dict[str, object] = {"close": close_price}
    if open_price is not None:
        overrides["open"] = open_price
    if payload_overrides:
        overrides.update(payload_overrides)
    payload = make_ta_payload(**overrides)
    if open_price is None:
        payload.pop("open", None)
    TASnapshot.objects.create(
        symbol="RELIANCE",
        exchange="NSE",
        timeframe="1D",
        pine_id="long_momentum@tv",
        pine_version="5",
        indicators={"vwap": payload["vwap"], "ema_20": payload["ema_20"]},
        raw_payload=payload,
        snapshot_timestamp=timestamp,
    )


@pytest.fixture
def seed_session_facts(monkeypatch):
    """Market-data session facts the intelligence enrichment reads.

    Opening 15-minute candle + trailing daily candles for RELIANCE, and a
    patched market calendar so every day is a trading day.
    """
    from apps.market_data.infrastructure.models import Candle, Instrument
    from core.market_calendar import MarketCalendar

    monkeypatch.setattr(MarketCalendar, "is_trading_day", lambda self, day: True)

    Instrument.objects.create(
        instrument_token=1002,
        exchange="NSE",
        tradingsymbol="RELIANCE",
        name="Reliance Industries Ltd (Research Integrity)",
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


def register_all_handlers(bus) -> None:
    """Register intelligence + rule_engine + risk_management on the bus."""
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


@pytest.fixture(autouse=True)
def _fake_event_bus(settings) -> None:
    """In-memory event bus so no Redis dependency and events are observable."""
    from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus

    settings.EVENT_BUS_IMPLEMENTATION = "fake"
    reset_event_bus()
    yield
    reset_event_bus()


@pytest.fixture(autouse=True)
def _execution_gate(settings) -> None:
    """Backtest replay must exercise the activated execution path."""
    settings.EXECUTION_ENGINE_ENABLED = True


@pytest.fixture
def active_bus(_fake_event_bus):
    from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

    return get_event_bus()


@pytest.fixture
def replay(seed_session_facts):
    """A runnable replay environment: seeded session facts + handlers."""

    def _replay(
        seed_bars: list[tuple[datetime, str | None, str]] | None = None,
        **run_overrides,
    ):
        """Seed bars as ``(timestamp, open, close)`` tuples, then run.

        ``open=None`` builds a bar without an ``open`` field (look-ahead
        fail-safe probe).
        """
        from apps.backtesting.services import BacktestRunnerService
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

        if seed_bars:
            for timestamp, open_price, close_price in seed_bars:
                seed_bar(timestamp, open_price=open_price, close_price=close_price)
        run = make_run(**run_overrides)
        bus = get_event_bus()
        register_all_handlers(bus)
        result = BacktestRunnerService().run(run.id)
        run.refresh_from_db()
        return run, result, bus

    return _replay


__all__ = [
    "BASE",
    "RUN_END",
    "RUN_START",
    "make_run",
    "make_ta_payload",
    "register_all_handlers",
    "seed_bar",
    "seed_session_facts",
]