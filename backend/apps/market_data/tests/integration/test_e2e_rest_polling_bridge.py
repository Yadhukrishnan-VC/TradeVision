"""E2E tests for the REST polling bridge (Batches M4 + M5.1).

Two complementary proofs (per the approved plan):

A) ``TestConstrainedRESTPoll`` — the FULL real polling path
   (``poll_market_data_watchlist`` -> backfill -> candle->TA bridge -> TA
   ingestion seam -> intelligence -> rule_engine) is driven against REST-only
   OHLCV. Indicator-dependent rules fail closed, and the only rules that can
   fire (``price_movement_v1`` / ``volume_spike_v1``) produce NO entry/stop
   levels, so Risk Management rejects them — the pipeline ends at
   ``RiskRejected`` with ZERO orders/fills. A second identical poll proves
   the marker prevents any duplicate ingestion / duplicate path.

B) ``TestTail`` — drives the same real ``TechnicalAnalysisIngestionService``
   seam with a crafted payload that DOES carry indicator values (the way
   backtest replay already does) and proves the real event-driven tail
   reaches Order -> Fill exactly once, with full correlation traceability.

C) ``TestIndicatorDrivenRESTPoll`` — M5 proof that the REST bridge itself now
   computes real VWAP/EMA20/ATR14/Bollinger-Upper from seeded persisted
   history, which lets the previously-REST-dead indicator rule
   ``long_momentum_v1`` fire with real entry/stop levels and reach
   RiskApproved -> Order -> Fill exactly once.

M5.1 (multi-timeframe session facts): the 15-minute and 1D frames are NO
LONGER fixture-seeded. ``FakeProvider`` is interval-aware and the real
``HistoricalSyncService.backfill`` path (driven from inside each poll) persists
them, so ``SessionFactsService`` reads genuinely real pipeline rows exactly as
production would. ``NOW`` is derived from the real current date (at a fixed
12:00 IST instant), keeping fixtures aligned with the wall-clock
``occurred_at`` used by the event bus regardless of which day the suite runs.

Every consumer is the real production handler wired on the FakeEventBus.
EXECUTION_ENGINE_ENABLED stays False in Test A (production default) and is
enabled in Tests B and C exactly like the other execution integration tests.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from datetime import time as dtime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from core.market_calendar import MarketSession
from core.market_data.base_provider import MarketDataResponse, OHLCVBar

_IST = ZoneInfo("Asia/Kolkata")


def _fixed_clock_now() -> datetime:
    """A reproducible "now" on the CURRENT trading day at 12:00 IST.

    Production event timestamps come from the real wall clock
    (``DomainEvent.occurred_at``); fixtures and the polling clock are pinned to
    ``NOW``. Deriving ``NOW`` from the same wall-clock date keeps every session
    fact (opening 15m candle, previous-day OHLC) on the same IST trading day
    reggedardless of the real date the suite is run — fixing the M5 date-flake.
    """
    today_ist = datetime.now(timezone.utc).astimezone(_IST).date()
    return datetime.combine(today_ist, dtime(12, 0), tzinfo=_IST).astimezone(
        timezone.utc
    )


NOW = _fixed_clock_now()

pytestmark = pytest.mark.django_db


class FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def set(self, key: str, value: str) -> None:
        self._store[key] = value


class FakeCalendar:
    def __init__(self, session: MarketSession) -> None:
        self._session = session

    def get_session(self, dt: datetime) -> MarketSession:
        return self._session


def _day_open_utc(day: datetime.date) -> datetime:
    """09:15 IST session-open instant for *day* (UTC)."""
    return datetime.combine(day, dtime(9, 15), tzinfo=_IST).astimezone(timezone.utc)


class FakeProvider:
    """Interval-aware deterministic provider for the FULL polling path.

    ``HistoricalSyncService`` requests bars for every timeframe the bridge
    polls — the operating window (``1min``) plus, under M5.1, the session
    frames ``15min`` and ``1D``. Each interval returns bars on its natural
    boundaries so the persisted doubles are real, session-aligned history:
        * ``1min``  — the M4 two-bar intraday snapshot (prior + fresh).
        * ``15min`` — a 09:15 IST opening bar for every calendar day in the
          requested range (opening 15-min candle + prior sessions).
        * ``1D``    — an end-of-last-30-sessions bar per day (prev-day OHLC
          + rolling average volume).
    """

    provider_name = "fake"

    def fetch(self, request: Any) -> MarketDataResponse:
        interval = request.interval
        if interval == "15min":
            bars = self._bars_15m(request)
        elif interval == "1D":
            bars = self._bars_1d()
        else:
            bars = self._bars_1m()
        return MarketDataResponse(
            request_id=request.request_id,
            symbol=request.symbol,
            interval=interval,
            bars=tuple(bars),
            provider=self.provider_name,
            fetched_at=NOW,
        )

    def _bars_1m(self) -> list[OHLCVBar]:
        prior_ts = NOW - timedelta(seconds=240)
        fresh_ts = NOW - timedelta(seconds=60)
        return [
            OHLCVBar(
                timestamp=prior_ts,
                open_price=Decimal("100.00"),
                high=Decimal("100.50"),
                low=Decimal("99.50"),
                close_price=Decimal("100.50"),
                volume=90_000,
            ),
            OHLCVBar(
                timestamp=fresh_ts,
                open_price=Decimal("103.00"),
                high=Decimal("104.00"),
                low=Decimal("102.00"),
                close_price=Decimal("103.00"),
                volume=1_000_000,
            ),
        ]

    def _bars_15m(self, request: Any) -> list[OHLCVBar]:
        barras: list[OHLCVBar] = []
        today = NOW.astimezone(_IST).date()
        first_day = (request.from_timestamp.astimezone(_IST).date() if request.from_timestamp else today)
        for offset in range(25):
            day = today - timedelta(days=offset)
            if day < first_day:
                break
            ts = _day_open_utc(day)
            if ts < NOW:
                barras.append(
                    OHLCVBar(
                        timestamp=ts,
                        open_price=Decimal("100.00"),
                        high=Decimal("100.00"),
                        low=Decimal("100.00"),
                        close_price=Decimal("100.00"),
                        volume=500_000,
                    )
                )
        bars = sorted(barras, key=lambda b: b.timestamp)
        return [b for b in bars if b.timestamp >= request.from_timestamp]

    def _bars_1d(self) -> list[OHLCVBar]:
        barras: list[OHLCVBar] = []
        today = NOW.astimezone(_IST).date()
        for offset in range(1, 31):
            day = today - timedelta(days=offset)
            barras.append(
                OHLCVBar(
                    timestamp=_day_open_utc(day),
                    open_price=Decimal("100.00"),
                    high=Decimal("110.00"),
                    low=Decimal("99.00"),
                    close_price=Decimal("103.00"),
                    volume=100_000,
                )
            )
        return barras

    def validate_connection(self) -> bool:
        return True

    def health_check(self) -> dict[str, Any]:
        return {"status": "healthy", "provider": self.provider_name, "latency_ms": 1.0}

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Deterministic market-data seeding
# ---------------------------------------------------------------------------


def _seed_instrument(monkeypatch, db) -> None:
    """Instrument row + all-days-trading calendar (remove pragmatic seeding)."""
    from apps.market_data.infrastructure.models import Instrument
    from core.market_calendar import MarketCalendar

    monkeypatch.setattr(MarketCalendar, "is_trading_day", lambda self, day: True)
    Instrument.objects.create(
        instrument_token=1001,
        exchange="NSE",
        tradingsymbol="RELIANCE",
        name="Reliance Industries Ltd (M4 E2E)",
        segment="EQUITY",
        lot_size=1,
        tick_size=Decimal("0.05"),
        instrument_type="EQ",
    )


def _configure_fake_bus_and_risk_gates(monkeypatch, db) -> None:
    """Route the FakeEventBus and force the risk gates open (deterministic)."""
    from django.conf import settings as dj_settings

    from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus
    from apps.risk_management.gateways.market_calendar_status_gateway import (
        MarketCalendarStatusGateway,
    )

    dj_settings.EVENT_BUS_IMPLEMENTATION = "fake"
    reset_event_bus()
    monkeypatch.setattr(
        MarketCalendarStatusGateway, "is_market_open", lambda self, dt: True
    )
    monkeypatch.setattr(MarketCalendarStatusGateway, "is_fresh", lambda self, a, r: True)


def _poll_runtime(monkeypatch, settings) -> Any:
    """Configure the deterministic polling runtime; returns the live bridge."""
    from unittest.mock import MagicMock

    from apps.market_data.application.candle_ta_bridge import (
        CandleToTechnicalAnalysisBridge,
    )
    from apps.market_data.application.historical_sync_service import (
        HistoricalSyncService,
    )

    settings.MARKET_DATA_POLL_TIMEFRAME = "1min"
    settings.MARKET_DATA_POLL_WINDOW_SECONDS = 600
    settings.MARKET_DATA_POLL_STALENESS_SECONDS = 180
    settings.MARKET_DATA_POLL_WATCHLIST = [("NSE", "RELIANCE")]

    monkeypatch.setattr(
        "apps.market_data.infrastructure.polling_tasks.get_now", lambda: NOW
    )
    monkeypatch.setattr(
        "apps.market_data.infrastructure.polling_tasks.get_ist_now", lambda: NOW
    )
    monkeypatch.setattr(
        "apps.market_data.application.candle_ta_bridge.get_now", lambda: NOW
    )
    monkeypatch.setattr(
        "apps.market_data.infrastructure.polling_tasks.get_market_calendar",
        lambda: FakeCalendar(MarketSession.MARKET_HOURS),
    )

    service = HistoricalSyncService()
    breaker = MagicMock()
    breaker.call.side_effect = lambda func, *args, **kwargs: func(*args, **kwargs)
    factory = MagicMock()
    factory.get_or_create.return_value = breaker
    service._circuit_factory = factory
    monkeypatch.setattr(
        "apps.market_data.infrastructure.polling_tasks.get_historical_sync_service",
        lambda: service,
    )
    monkeypatch.setattr(
        "apps.market_data.application.historical_sync_service.MarketDataProviderFactory.get_provider",
        lambda: FakeProvider(),
    )

    bridge = CandleToTechnicalAnalysisBridge(
        redis_client=FakeRedis(), staleness_seconds=180
    )
    monkeypatch.setattr(
        "apps.market_data.infrastructure.polling_tasks.get_candle_ta_bridge",
        lambda: bridge,
    )
    return bridge


def _backfill_session_frames_direct(monkeypatch, db) -> None:
    """Persist 15m + 1D session rows via the REAL provider->sync path.

    Used by Test B (crafted payload) which bypasses the polling cycle but still
    needs the same real session history. Mirrors exactly what
    ``poll_watchlist_sync`` does under M5.1: request the 15-minute and 1D frames
    through ``HistoricalSyncService.backfill`` with the interval-aware provider
    and the same circuit-breaker bypass used by ``_poll_runtime``.
    """
    from unittest.mock import MagicMock

    from apps.market_data.application.historical_sync_service import (
        HistoricalSyncService,
    )
    from apps.market_data.domain.value_objects import Timeframe

    service = HistoricalSyncService()
    breaker = MagicMock()
    breaker.call.side_effect = lambda func, *args, **kwargs: func(*args, **kwargs)
    factory = MagicMock()
    factory.get_or_create.return_value = breaker
    service._circuit_factory = factory
    monkeypatch.setattr(
        "apps.market_data.application.historical_sync_service.MarketDataProviderFactory.get_provider",
        lambda: FakeProvider(),
    )

    service.backfill(
        instrument_token=1001,
        timeframe=Timeframe.MINUTE_15,
        from_timestamp=NOW - timedelta(days=20),
        to_timestamp=NOW,
    )
    service.backfill(
        instrument_token=1001,
        timeframe=Timeframe.DAY_1,
        from_timestamp=NOW - timedelta(days=30),
        to_timestamp=NOW,
    )


def _configure_fake_bus_and_risk_gates_b(monkeypatch, db) -> None:
    """Alias kept for the Tail test (same risk gates; no poll)."""
    _configure_fake_bus_and_risk_gates(monkeypatch, db)


def _register_handlers(bus, *register_handlers) -> None:
    for register in register_handlers:
        register(bus)


def _make_account(db, django_user_model) -> Any:
    from apps.accounts.infrastructure.models import Account
    from apps.portfolio.application.capital_service import CapitalService

    user = django_user_model.objects.create_user(
        username=f"m4e2e_{uuid.uuid4().hex[:8]}", password="p"
    )
    account = Account.objects.create(name="Primary", owner=user, is_default=True)
    CapitalService().deposit(account.id, Decimal(1000000))
    return account


def _seed_minute_history(db, count: int = 60) -> None:
    """Seed `count` 1-minute candles inside the current session (10:16 IST+).

    Constant flat bars (close 100.00, volume 1000 each) so the shared
    60-candle indicator window reaches the EMA20 warm-up gate *before* the
    polled bars arrive via the IntervalAwareProvider.
    """
    from apps.market_data.infrastructure.models import Candle

    session_day = NOW.astimezone(_IST).date()
    start = datetime.combine(session_day, dtime(10, 16), tzinfo=_IST).astimezone(
        timezone.utc
    )
    for idx in range(count):
        Candle.objects.create(
            instrument_id=1001,
            timeframe="1min",
            timestamp=start + timedelta(minutes=idx),
            open=Decimal("100.00"),
            high=Decimal("100.50"),
            low=Decimal("99.50"),
            close=Decimal("100.00"),
            volume=1000,
        )


# ---------------------------------------------------------------------------
# Test A — constrained REST bridge: full chain ends at RiskRejected
# ---------------------------------------------------------------------------


class TestConstrainedRESTPoll:
    def _setup(self, monkeypatch, settings, db):
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
        from apps.intelligence.infrastructure.event_handlers import (
            register_handlers as register_intelligence,
        )
        from apps.risk_management.infrastructure.event_handlers import (
            register_handlers as register_risk,
        )
        from apps.rule_engine.infrastructure.event_handlers import (
            register_handlers as register_rule,
        )

        _seed_instrument(monkeypatch, db)
        _configure_fake_bus_and_risk_gates(monkeypatch, db)
        bridge = _poll_runtime(monkeypatch, settings)

        bus = get_event_bus()
        _register_handlers(bus, register_intelligence, register_rule, register_risk)
        return bus, bridge

    def test_rest_poll_drives_chain_to_risk_rejected_no_orders(
        self, monkeypatch, settings, db
    ) -> None:
        from apps.execution.infrastructure.models import ExecutionRequest, Fill, Order
        from apps.market_data.infrastructure.polling_tasks import (
            poll_market_data_watchlist,
        )
        from apps.risk_management.infrastructure.models import RiskDecisionExecution
        from apps.technical_analysis.infrastructure.models import TASnapshot

        bus, _ = self._setup(monkeypatch, settings, db)

        poll_market_data_watchlist.apply().get()

        # ------------------------------------------------------------------
        # Ingestion layer: exactly one candle pachado / via seam
        # ------------------------------------------------------------------
        ta_events = [
            e for e in bus.published_events
            if e.event_type == "technical_analysis.TechnicalAnalysisCompleted"
        ]
        assert len(ta_events) == 1
        ta_event = ta_events[0]
        assert ta_event.payload["symbol"] == "RELIANCE"
        assert ta_event.payload["timeframe"] == "1min"
        assert Decimal(ta_event.payload["price"]["close"]) == Decimal("103.00")
        assert Decimal(ta_event.payload["price"]["change_pct"]) == Decimal("2.4876")
        # M5 bridge: only the session-minimal VWAP is emitted here because the
        # 1-min history is too shallow for the 60/15/20 fixed windows.
        assert set(ta_event.payload["indicators"]) == {"vwap"}
        assert Decimal(ta_event.payload["indicators"]["vwap"]) > 0
        assert TASnapshot.objects.filter(
            symbol="RELIANCE", timeframe="1min"
        ).count() == 1

        # ------------------------------------------------------------------
        # M5.1 — the 15m + 1D session frames are now genuinely persisted by
        # the pipeline (interval-aware provider) and read by SessionFacts.
        # ------------------------------------------------------------------
        from apps.market_data.application.session_facts_service import (
            SessionFactsService,
        )
        from apps.market_data.infrastructure.models import Candle as CandleModel

        assert CandleModel.objects.filter(
            instrument_id=1001, timeframe="15min"
        ).exists()
        assert CandleModel.objects.filter(
            instrument_id=1001, timeframe="1D"
        ).exists()
        facts = SessionFactsService()
        assert facts.get_opening_15m_candle(1001, NOW) is not None
        assert facts.get_previous_day_ohlc(1001, NOW) != (None, None)
        assert facts.get_avg_daily_volume(1001, NOW, days=10) == Decimal(100000)

        # ------------------------------------------------------------------
        # Intelligence: packet built with REST facts (vwap, no fixed windows)
        # ------------------------------------------------------------------
        packet_events = [
            e for e in bus.published_events
            if e.event_type == "intelligence.PacketBuilt"
        ]
        assert len(packet_events) == 1
        packet_event = packet_events[0]
        assert packet_event.correlation_id == ta_event.correlation_id
        assert packet_event.causation_id == ta_event.event_id

        # ------------------------------------------------------------------
        # Rule engine: only REST-capable rules fire; NO indicator rule fires
        # ------------------------------------------------------------------
        fired_events = [
            e for e in bus.published_events
            if e.event_type == "rule_engine.RuleFired"
        ]
        fired_rule_ids = {e.payload["rule_id"] for e in fired_events}
        assert fired_rule_ids == {"price_movement_v1", "volume_spike_v1"}
        forbidden = {
            "long_momentum_v1",
            "short_sell_v1",
            "volatility_breakout_v1",
            "breakout_v1",
        }
        assert not (fired_rule_ids & forbidden)

        for fired in fired_events:
            assert "entry_price" not in fired.payload["trigger_data"]
            assert "stop_loss" not in fired.payload["trigger_data"]

        # ------------------------------------------------------------------
        # Risk management: fail-closed — both rejected, zero approvals
        # ------------------------------------------------------------------
        rejected_events = [
            e for e in bus.published_events
            if e.event_type == "risk_management.RiskRejected"
        ]
        assert len(rejected_events) == 2
        assert {e.payload["rule_id"] for e in rejected_events} == fired_rule_ids
        assert not [
            e for e in bus.published_events
            if e.event_type == "risk_management.RiskApproved"
        ]

        decisions = RiskDecisionExecution.objects.all()
        assert decisions.count() == 2
        assert {d.status for d in decisions} == {"REJECTED"}
        assert {d.rejection_code for d in decisions} == {"MISSING_STOP_LOSS"}

        # ------------------------------------------------------------------
        # Execution: the pipeline must stop before any order is touched
        # ------------------------------------------------------------------
        assert ExecutionRequest.objects.count() == 0
        assert Order.objects.count() == 0
        assert Fill.objects.count() == 0

        assert not [
            e for e in bus.published_events
            if e.event_type.startswith(("ai_engine.", "pattern_engine."))
        ]

    def test_repoll_does_not_reingest_or_duplicate_any_path(
        self, monkeypatch, settings, db
    ) -> None:
        from apps.execution.infrastructure.models import ExecutionRequest, Order
        from apps.market_data.infrastructure.polling_tasks import (
            poll_market_data_watchlist,
        )
        from apps.risk_management.infrastructure.models import RiskDecisionExecution
        from apps.technical_analysis.infrastructure.models import TASnapshot

        bus, _ = self._setup(monkeypatch, settings, db)

        poll_market_data_watchlist.apply().get()
        counts_after_first = {
            "ta": TASnapshot.objects.count(),
            "packets": len(
                [
                    e for e in bus.published_events
                    if e.event_type == "intelligence.PacketBuilt"
                ]
            ),
            "risk": RiskDecisionExecution.objects.count(),
        }
        assert counts_after_first["ta"] == 1
        # M5.1 gate cadence: once the 15m opening candle + prev-day OHLC exist,
        # the second poll skips both frames (self-limiting per session).
        from apps.market_data.infrastructure.models import Candle as CandleModel

        first_15m = CandleModel.objects.filter(
            instrument_id=1001, timeframe="15min"
        ).count()
        first_1d = CandleModel.objects.filter(
            instrument_id=1001, timeframe="1D"
        ).count()

        poll_market_data_watchlist.apply().get()

        assert TASnapshot.objects.count() == counts_after_first["ta"]
        assert len(
            [
                e for e in bus.published_events
                if e.event_type == "intelligence.PacketBuilt"
            ]
        ) == counts_after_first["packets"]
        assert RiskDecisionExecution.objects.count() == counts_after_first["risk"]
        assert ExecutionRequest.objects.count() == 0
        assert Order.objects.count() == 0
        # Frames stay stable across repoll (idempotent upsert + gate skip).
        assert CandleModel.objects.filter(
            instrument_id=1001, timeframe="15min"
        ).count() == first_15m
        assert CandleModel.objects.filter(
            instrument_id=1001, timeframe="1D"
        ).count() == first_1d


# ---------------------------------------------------------------------------
# Test B — tail proof: same real seam + indicator data reaches Order/Fill once
# ---------------------------------------------------------------------------


class TestTail:
    def test_indicator_loaded_seam_reaches_single_order_and_fill(
        self, monkeypatch, settings, db, django_user_model
    ) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
        from apps.execution.domain.value_objects import side_for_rule
        from apps.execution.infrastructure.models import ExecutionRequest, Fill, Order
        from apps.execution.infrastructure.tasks import handle_risk_approved
        from apps.intelligence.infrastructure.event_handlers import (
            register_handlers as register_intelligence,
        )
        from apps.risk_management.infrastructure.event_handlers import (
            register_handlers as register_risk,
        )
        from apps.risk_management.infrastructure.models import RiskDecisionExecution
        from apps.rule_engine.infrastructure.event_handlers import (
            register_handlers as register_rule,
        )
        from apps.rule_engine.infrastructure.models import RuleExecution
        from apps.technical_analysis.application.services import (
            TechnicalAnalysisIngestionService,
        )
        from apps.technical_analysis.infrastructure.repositories import (
            TASnapshotRepository,
        )

        settings.EXECUTION_ENGINE_ENABLED = True
        # Real session-history frames (no fixture Candle.create), plus the
        # instrument. Test B bypasses the poll cycle by design (it crafts a
        # payload through the TA seam), so it navigates the same backfill path
        # directly through the real provider+sync service.
        _seed_instrument(monkeypatch, db)
        _backfill_session_frames_direct(monkeypatch, db)
        _configure_fake_bus_and_risk_gates(monkeypatch, db)
        account = _make_account(db, django_user_model)

        bus = get_event_bus()
        _register_handlers(bus, register_intelligence, register_rule, register_risk)

        fresh_ts = NOW - timedelta(seconds=60)
        payload: dict[str, Any] = {
            "ticker": "RELIANCE",
            "exchange": "NSE",
            "timeframe": "1min",
            "open": "103.00",
            "high": "104.00",
            "low": "102.00",
            "close": "103.00",
            "volume": 1_000_000,
            "time": int(fresh_ts.timestamp() * 1000),
            "prev_close": "100.50",
            "change_pct": "2.4876",
            # Crafted indicator values that make Setup-1 fire:
            "vwap": "101.50",
            "ema_20": "102.00",
        }

        correlation_id = uuid.uuid4()
        service = TechnicalAnalysisIngestionService(
            repository=TASnapshotRepository(),
            event_bus=bus,
        )
        service.ingest(payload, correlation_id=correlation_id)

        # ------------------------------------------------------------------
        # Full real cascade through to a single order + fill
        # ------------------------------------------------------------------
        ta_event = next(
            e for e in bus.published_events
            if e.event_type == "technical_analysis.TechnicalAnalysisCompleted"
        )
        packet_event = next(
            e for e in bus.published_events
            if e.event_type == "intelligence.PacketBuilt"
        )

        # This crafted payload is NOT REST-only: it carries the two indicators
        # Setup-1 needs. The REST-only rules still fire too, but the only
        # RULE that carries entry/stop levels is long_momentum_v1 — it alone
        # is approval-eligible. Everything else fails closed.
        fired_events = [
            e for e in bus.published_events
            if e.event_type == "rule_engine.RuleFired"
        ]
        fired_rule_ids = {e.payload["rule_id"] for e in fired_events}
        assert fired_rule_ids == {
            "price_movement_v1",
            "volume_spike_v1",
            "long_momentum_v1",
        }
        fired_event = next(
            e for e in fired_events if e.payload["rule_id"] == "long_momentum_v1"
        )
        approved_event = next(
            e for e in bus.published_events
            if e.event_type == "risk_management.RiskApproved"
        )
        rejected_events = [
            e for e in bus.published_events
            if e.event_type == "risk_management.RiskRejected"
        ]

        assert approved_event.payload["rule_id"] == "long_momentum_v1"
        assert len(rejected_events) == 2
        assert {e.payload["rule_id"] for e in rejected_events} == {
            "price_movement_v1",
            "volume_spike_v1",
        }

        assert Decimal(
            fired_event.payload["trigger_data"]["entry_price"]
        ) == Decimal("103.00")
        assert Decimal(
            fired_event.payload["trigger_data"]["stop_loss"]
        ) == Decimal("100.00")

        packet_data = packet_event.payload["packet_data"]
        tech_ctx = packet_data["technical_context"]
        price_ctx = packet_data["price_context"]
        assert Decimal(tech_ctx["vwap"]) == Decimal("101.50")
        assert Decimal(tech_ctx["ema_20"]) == Decimal("102.00")
        assert Decimal(price_ctx["avg_volume_20d"]) == Decimal(100000)
        # M5.1: real framework fact — opening candle / previous day via the
        # session-frames backfill.
        assert tech_ctx["opening_15m_open"] is not None

        assert ExecutionRequest.objects.count() == 1
        assert Order.objects.count() == 1
        assert Fill.objects.count() >= 1

        order = Order.objects.get()
        assert order.status == "FILLED"
        assert order.symbol == "RELIANCE"
        assert order.side == side_for_rule("long_momentum_v1").value
        assert order.avg_fill_price == Decimal("103.00")
        assert order.entry_price == Decimal("103.00")
        assert order.stop_loss == Decimal("100.00")

        request = ExecutionRequest.objects.get()
        assert request.account_id == account.id
        assert request.risk_approved_event_id == approved_event.event_id
        assert len(rejected_events) == 2

        # ------------------------------------------------------------------
        # Traceability: correlation/causation threaded end-to-end
        # ------------------------------------------------------------------
        assert packet_event.correlation_id == correlation_id
        assert packet_event.causation_id == ta_event.event_id
        assert fired_event.correlation_id == packet_event.event_id
        assert approved_event.correlation_id == packet_event.event_id
        assert approved_event.causation_id == fired_event.event_id
        assert request.correlation_id == approved_event.correlation_id
        assert order.correlation_id == request.correlation_id

        # ------------------------------------------------------------------
        # No duplicate Order/Fill on redelivered approval
        # ------------------------------------------------------------------
        result = handle_risk_approved.run(
            payload=approved_event.payload,
            correlation_id=str(approved_event.correlation_id),
            causation_id=str(approved_event.causation_id or ""),
            risk_approved_event_id=str(approved_event.event_id),
        )
        assert result["outcome"] in {"DUPLICATE", "duplicate"}
        assert ExecutionRequest.objects.count() == 1
        assert Order.objects.count() == 1

        # redelivered RuleFired is deduped before a second approval can exist
        from apps.eventbus.domain.events import DomainEvent

        bus.publish(
            DomainEvent.create(
                event_type="rule_engine.RuleFired",
                payload=fired_event.payload,
                correlation_id=fired_event.correlation_id,
                causation_id=fired_event.causation_id,
            )
        )
        assert RuleExecution.objects.filter(
            rule_id="long_momentum_v1",
            analysis_event_id=uuid.UUID(fired_event.payload["analysis_event_id"]),
        ).count() == 1
        assert RiskDecisionExecution.objects.filter(
            rule_id="long_momentum_v1",
            analysis_event_id=uuid.UUID(fired_event.payload["analysis_event_id"]),
        ).count() == 1
        assert Order.objects.count() == 1


# ---------------------------------------------------------------------------
# Test C — M5 proof: real indicators from the REST bridge drive a real rule
# ---------------------------------------------------------------------------


class TestIndicatorDrivenRESTPoll:
    """Run the FULL real polling path with seeded 1-minute history so the M5
    bridge computes real VWAP/EMA20/ATR14/Bollinger-Upper. With all four
    indicators present, ``long_momentum_v1`` — an indicator-dependent rule
    that M4 could never fire on REST data — now fires with a real stop and
    reaches RiskApproved -> Order -> Fill exactly once.

    M5.1: the 15m/1D session facts are produced by the polling pipeline itself
    (not seeded), proving the session-facts -> rule input contract end to end.
    """

    def _setup(self, monkeypatch, settings, db, django_user_model):
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
        from apps.intelligence.infrastructure.event_handlers import (
            register_handlers as register_intelligence,
        )
        from apps.risk_management.infrastructure.event_handlers import (
            register_handlers as register_risk,
        )
        from apps.rule_engine.infrastructure.event_handlers import (
            register_handlers as register_rule,
        )

        _seed_instrument(monkeypatch, db)
        _seed_minute_history(db, count=60)
        _configure_fake_bus_and_risk_gates(monkeypatch, db)
        settings.EXECUTION_ENGINE_ENABLED = True
        account = _make_account(db, django_user_model)

        bridge = _poll_runtime(monkeypatch, settings)
        bus = get_event_bus()
        _register_handlers(bus, register_intelligence, register_rule, register_risk)
        return bus, bridge, account

    def test_real_bridge_indicators_fire_long_momentum_and_fill(
        self, monkeypatch, settings, db, django_user_model
    ) -> None:
        from apps.execution.infrastructure.models import ExecutionRequest, Fill, Order
        from apps.market_data.infrastructure.polling_tasks import (
            poll_market_data_watchlist,
        )

        bus, _, account = self._setup(monkeypatch, settings, db, django_user_model)

        poll_market_data_watchlist.apply().get()

        # ------------------------------------------------------------------
        # M5 bridge: all four indicators computed from seeded persisted history
        # ------------------------------------------------------------------
        ta_event = next(
            e for e in bus.published_events
            if e.event_type == "technical_analysis.TechnicalAnalysisCompleted"
        )
        assert set(ta_event.payload["indicators"]) == {"vwap", "ema_20", "atr_14", "bb_upper"}
        for value in ta_event.payload["indicators"].values():
            assert Decimal(value) > 0

        packet_data = next(
            e for e in bus.published_events
            if e.event_type == "intelligence.PacketBuilt"
        ).payload["packet_data"]
        tech_ctx = packet_data["technical_context"]
        assert Decimal(tech_ctx["vwap"]) == Decimal(ta_event.payload["indicators"]["vwap"])
        assert Decimal(tech_ctx["ema_20"]) == Decimal(ta_event.payload["indicators"]["ema_20"])
        # M5.1 session facts read from the REAL pipeline rows.
        assert tech_ctx["opening_15m_open"] is not None
        assert tech_ctx["opening_15m_low"] is not None
        assert tech_ctx["prev_day_high"] is not None
        assert tech_ctx["prev_day_low"] is not None

        # ------------------------------------------------------------------
        # The indicator-dependent rule now fires with real entry/stop levels
        # ------------------------------------------------------------------
        fired_ids = {
            e.payload["rule_id"]
            for e in bus.published_events
            if e.event_type == "rule_engine.RuleFired"
        }
        assert "long_momentum_v1" in fired_ids

        long_fired = next(
            e for e in bus.published_events
            if e.event_type == "rule_engine.RuleFired"
            and e.payload["rule_id"] == "long_momentum_v1"
        )
        entry = Decimal(long_fired.payload["trigger_data"]["entry_price"])
        stop = Decimal(long_fired.payload["trigger_data"]["stop_loss"])
        # entry=103 (> VWAP/EMA), stop = min(opening_low=100, vwap >100) => 100
        assert entry == Decimal("103.00")
        assert stop == Decimal("100.00")

        # ------------------------------------------------------------------
        # Risk: approved once; other fired rules rejected (no stop levels)
        # ------------------------------------------------------------------
        approved = [
            e for e in bus.published_events
            if e.event_type == "risk_management.RiskApproved"
        ]
        assert len(approved) == 1
        assert approved[0].payload["rule_id"] == "long_momentum_v1"

        rejected = [
            e for e in bus.published_events
            if e.event_type == "risk_management.RiskRejected"
        ]
        assert {e.payload["rule_id"] for e in rejected} == fired_ids - {"long_momentum_v1"}
        assert all(e.payload["reason_code"] == "MISSING_STOP_LOSS" for e in rejected)

        # ------------------------------------------------------------------
        # Execution: exactly one order, filled once, priced at the rule entry
        # ------------------------------------------------------------------
        assert ExecutionRequest.objects.count() == 1
        assert Order.objects.count() == 1
        assert Fill.objects.count() >= 1

        order = Order.objects.get()
        assert order.status == "FILLED"
        assert order.symbol == "RELIANCE"
        assert order.avg_fill_price == entry
        assert order.entry_price == entry
        assert order.stop_loss == stop

        request = ExecutionRequest.objects.get()
        assert request.account_id == account.id
        assert request.risk_approved_event_id == approved[0].event_id

        # traceability threaded from the TA event to the fill bearer
        assert order.correlation_id == request.correlation_id == approved[0].correlation_id