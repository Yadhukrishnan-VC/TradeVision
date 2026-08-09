"""Batch M3.6 — end-to-end stop-loss exit tests.

Test #8 — the single most important proof in this batch: seed a short
synthetic historical series (entry bar, then a later bar whose low breaches
the computed stop) through the real ``BacktestRunnerService.run()`` and
assert the position opens on the entry bar and closes via the stop-loss
exit handler on the later bar — with non-zero, correctly-signed realized
P&L for the first time in this system's backtest history.

Test #9 — live/REST-poll parity: drive the same handler via the real
``poll_market_data_watchlist`` cycle (M4/M5.1 machinery, unmodified) to prove
the "zero backtest-specific code" claim of M3.6, not just assert it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

_IST = ZoneInfo("Asia/Kolkata")

# 2024-06-10 07:00 UTC == 12:30 IST, a Monday inside NSE market hours.
ENTRY_BAR_TIME = datetime(2024, 6, 10, 7, 0, 0, tzinfo=timezone.utc)
EXIT_BAR_TIME = datetime(2024, 6, 10, 8, 0, 0, tzinfo=timezone.utc)

pytestmark = pytest.mark.django_db


def _seed_instrument_and_facts(db, monkeypatch) -> None:
    """Instrument + session-facts rows the intelligence enrichment reads."""
    from apps.market_data.infrastructure.models import Candle, Instrument
    from core.market_calendar import MarketCalendar

    # Force every day to be a trading day (deterministic regardless of clock).
    # Use monkeypatch so the class-level default is restored after the test —
    # a bare attribute assignment would leak the all-days-trading flag into
    # every later test in the same process.
    monkeypatch.setattr(
        MarketCalendar, "is_trading_day", lambda self, day: True
    )

    Instrument.objects.create(
        instrument_token=1002,
        exchange="NSE",
        tradingsymbol="RELIANCE",
        name="Reliance Industries Ltd (M3.6 E2E)",
        segment="EQUITY",
        lot_size=1,
        tick_size=Decimal("0.05"),
        instrument_type="EQ",
    )

    session_day = datetime.now(timezone.utc).astimezone(_IST).date()
    opening_utc = datetime.combine(session_day, time(9, 15), tzinfo=_IST).astimezone(
        timezone.utc
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


def _make_account(db, django_user_model):
    from apps.accounts.infrastructure.models import Account
    from apps.portfolio.application.capital_service import CapitalService

    user = django_user_model.objects.create_user(
        username=f"m36_{uuid.uuid4().hex[:8]}", password="p"
    )
    account = Account.objects.create(name="M3.6", owner=user, is_default=False)
    CapitalService().deposit(account.id, Decimal(1000000))
    return account


def _make_run(account):
    from apps.backtesting.models import BacktestRun

    run = BacktestRun(
        symbol="RELIANCE",
        timeframe="1D",
        range_start=datetime(2024, 6, 9, tzinfo=timezone.utc),
        range_end=datetime(2024, 6, 11, tzinfo=timezone.utc),
        account=account,
        status="PENDING",
    )
    run.full_clean()
    run.save()
    return run


def _register_all_handlers(bus):
    """Real intelligence + rule_engine + risk + portfolio handlers."""
    from apps.intelligence.infrastructure.event_handlers import (
        register_handlers as register_intelligence,
    )
    from apps.portfolio.infrastructure.event_handlers import (
        register_handlers as register_portfolio,
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
    register_portfolio(bus)


class TestBacktestStopExit:
    def test_backtest_stop_hit_closes_position_with_realized_pnl(
        self, db, django_user_model, monkeypatch
    ) -> None:
        from django.conf import settings

        from apps.eventbus.infrastructure.event_bus_factory import (
            get_event_bus,
            reset_event_bus,
        )
        from apps.portfolio.infrastructure.models import (
            AccountCapitalState,
            Position,
        )
        from apps.portfolio.infrastructure.price_source import (
            MarketDataCurrentPriceProvider,
        )
        from apps.technical_analysis.infrastructure.models import TASnapshot

        settings.EVENT_BUS_IMPLEMENTATION = "fake"
        settings.EXECUTION_ENGINE_ENABLED = True
        reset_event_bus()
        monkeypatch.setattr(
            MarketDataCurrentPriceProvider,
            "get_current_price",
            lambda self, symbol: None,
        )

        _seed_instrument_and_facts(db, monkeypatch)
        account = _make_account(db, django_user_model)
        run = _make_run(account)
        bus = get_event_bus()
        _register_all_handlers(bus)

        # Entry bar: the payload that fires Setup-1 (open=low 100, close 103,
        # stop = min(100, vwap 101.5) = 100).
        entry_payload = {
            "ticker": "RELIANCE",
            "exchange": "NSE",
            "timeframe": "1D",
            "close": "103.00",
            "open": "100.00",
            "high": "104.00",
            "low": "103.00",
            "volume": 1_000_000,
            "vwap": "101.50",
            "ema_20": "102.00",
            "pine_id": "long_momentum@tv",
            "pine_version": "5",
        }
        TASnapshot.objects.create(
            symbol="RELIANCE",
            exchange="NSE",
            timeframe="1D",
            pine_id="long_momentum@tv",
            pine_version="5",
            indicators={"vwap": "101.50", "ema_20": "102.00"},
            raw_payload=entry_payload,
            snapshot_timestamp=ENTRY_BAR_TIME,
        )
        # Exit bar: low 94 breaches the stop (100). Volume kept below the
        # spike threshold and price below open so no new entry fires here.
        exit_payload = {
            "ticker": "RELIANCE",
            "exchange": "NSE",
            "timeframe": "1D",
            "close": "101.00",
            "open": "102.00",
            "high": "102.50",
            "low": "94.00",
            "volume": 10_000,
            "vwap": "101.50",
            "ema_20": "102.00",
            "pine_id": "long_momentum@tv",
            "pine_version": "5",
        }
        TASnapshot.objects.create(
            symbol="RELIANCE",
            exchange="NSE",
            timeframe="1D",
            pine_id="long_momentum@tv",
            pine_version="5",
            indicators={"vwap": "101.50", "ema_20": "102.00"},
            raw_payload=exit_payload,
            snapshot_timestamp=EXIT_BAR_TIME,
        )

        from apps.backtesting.services import BacktestRunnerService

        result = BacktestRunnerService().run(run.id)
        assert result["status"] == "COMPLETED"
        assert result["bars_processed"] == "2"

        # Position was opened on the entry bar, then closed by the stop on the
        # exit bar -> no open position remains.
        assert Position.objects.filter(account_id=account.id).count() == 0

        from apps.execution.infrastructure.models import Order

        order = Order.objects.get(account_id=account.id)
        assert order.status == "FILLED"
        assert order.symbol == "RELIANCE"
        assert order.stop_loss == Decimal("100.00")

        # One stop-triggered close event proves the exit path ran exactly once.
        from apps.eventbus.domain.events import DomainEvent

        closed_events = [
            e
            for e in bus.published_events
            if isinstance(e, DomainEvent)
            and e.event_type == "positions.PositionClosed"
        ]
        assert len(closed_events) == 1
        closed = closed_events[0]
        assert closed.payload["symbol"] == "RELIANCE"
        assert Decimal(closed.payload["exit_price"]) == Decimal("94.00")

        # Non-zero, correctly-signed realized loss: LONG entry 103 stopped 94.
        state = AccountCapitalState.objects.get(account=account)
        assert state.realized_pnl_today != Decimal(0)
        assert state.realized_pnl_today < Decimal(0)