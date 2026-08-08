"""Unit/integration tests for the REST polling bridge tasks (Batch M4).

Covers watchlist parsing, the market-hours guard, empty-watchlist/invalid
timeframe no-ops, per-symbol isolation, and the provider-outage retry path.
The full event cascade is proven by the E2E integration test.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest
from pytest import MonkeyPatch

from apps.market_data.application.candle_ta_bridge import (
    CandleToTechnicalAnalysisBridge,
)
from apps.market_data.application.historical_sync_service import HistoricalSyncService
from apps.market_data.domain.value_objects import Timeframe
from apps.market_data.infrastructure.models import Candle as CandleModel
from apps.market_data.infrastructure.models import Instrument as InstrumentModel
from apps.market_data.infrastructure.polling_tasks import (
    _parse_watchlist,
    poll_market_data_watchlist,
    poll_watchlist_sync,
)
from core.exceptions import DataProviderError
from core.market_calendar import MarketSession
from core.market_data.base_provider import MarketDataResponse, OHLCVBar

NOW = datetime(2026, 8, 8, 7, 0, 0, tzinfo=timezone.utc)


class FakeCalendar:
    def __init__(self, session: MarketSession) -> None:
        self._session = session

    def get_session(self, dt: datetime) -> MarketSession:
        return self._session


class FakeProvider:
    provider_name = "fake"

    def __init__(self, bars: list[OHLCVBar], *, fail: bool = False) -> None:
        self._bars = bars
        self.fail = fail

    def fetch(self, request: Any) -> MarketDataResponse:
        if self.fail:
            raise DataProviderError(f"provider down for {request.symbol}")
        # M5.1: the operating cycle is ``1min``; the 15m/1D session frames are
        # exercised by the interval-aware provider in the E2E integration test,
        # so this unit fake yields no bars for the supplementary frames.
        bars = self._bars if request.interval == "1min" else []
        return MarketDataResponse(
            request_id=request.request_id,
            symbol=request.symbol,
            interval=request.interval,
            bars=tuple(bars),
            provider=self.provider_name,
            fetched_at=NOW,
        )

    def validate_connection(self) -> bool:
        return True

    def health_check(self) -> dict[str, Any]:
        return {"status": "healthy", "provider": self.provider_name, "latency_ms": 1.0}

    def close(self) -> None:
        pass


def _bars(symbol_close: Decimal) -> list[OHLCVBar]:
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
            open_price=symbol_close,
            high=symbol_close + Decimal("1.00"),
            low=symbol_close - Decimal("1.00"),
            close_price=symbol_close,
            volume=1_000_000,
        ),
    ]


class FakeRedis:
    """Minimal dict-backed stand-in for the production Redis client."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def set(self, key: str, value: str) -> None:
        self._store[key] = value


@pytest.fixture(autouse=True)
def _isolate_singletons(monkeypatch: MonkeyPatch) -> None:
    """Keep the module singletons out of the test run."""
    from apps.market_data.application.candle_ta_bridge import reset_candle_ta_bridge
    from apps.market_data.application.historical_sync_service import (
        reset_historical_sync_service,
    )

    reset_candle_ta_bridge()
    reset_historical_sync_service()
    yield
    reset_candle_ta_bridge()
    reset_historical_sync_service()


@pytest.fixture(autouse=True)
def _fake_event_bus() -> None:
    """Route all published events through the in-memory bus for this module."""
    from django.conf import settings as dj_settings

    from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus

    dj_settings.EVENT_BUS_IMPLEMENTATION = "fake"
    reset_event_bus()
    yield
    reset_event_bus()


def _clock(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "apps.market_data.infrastructure.polling_tasks.get_now", lambda: NOW
    )
    monkeypatch.setattr(
        "apps.market_data.infrastructure.polling_tasks.get_ist_now", lambda: NOW
    )
    monkeypatch.setattr(
        "apps.market_data.application.candle_ta_bridge.get_now", lambda: NOW
    )


def _historical_service(monkeypatch: MonkeyPatch, provider: FakeProvider) -> HistoricalSyncService:
    service = HistoricalSyncService()
    breaker = MagicMock()
    breaker.call.side_effect = lambda func, *args, **kwargs: func(*args, **kwargs)
    factory = MagicMock()
    factory.get_or_create.return_value = breaker
    service._circuit_factory = factory
    monkeypatch.setattr(
        "apps.market_data.application.historical_sync_service.MarketDataProviderFactory.get_provider",
        lambda: provider,
    )
    monkeypatch.setattr(
        "apps.market_data.infrastructure.polling_tasks.get_historical_sync_service",
        lambda: service,
    )
    return service


def _seed_instrument(token: int, symbol: str, db: Any) -> None:
    InstrumentModel.objects.create(
        instrument_token=token,
        exchange="NSE",
        tradingsymbol=symbol,
        name=f"{symbol} Ltd",
        segment="EQUITY",
        lot_size=1,
        tick_size=Decimal("0.05"),
        instrument_type="EQ",
    )


# ---------------------------------------------------------------------------
# watchlist parsing
# ---------------------------------------------------------------------------


class TestParseWatchlist:
    def test_parses_and_normalises_pairs(self) -> None:
        assert _parse_watchlist("NSE:RELIANCE, bse:tcs, ,NSE:INFY") == [
            ("NSE", "RELIANCE"),
            ("BSE", "TCS"),
            ("NSE", "INFY"),
        ]

    def test_rejects_malformed_entry(self) -> None:
        with pytest.raises(ValueError, match="Expected 'EXCHANGE:SYMBOL'"):
            _parse_watchlist("NSE:RELIANCE,not-a-pair")

    def test_empty_string_returns_empty_list(self) -> None:
        assert _parse_watchlist("") == []


# ---------------------------------------------------------------------------
# guard no-ops
# ---------------------------------------------------------------------------


class TestPollGuards:
    def test_empty_watchlist_noop(self, db) -> None:
        assert poll_watchlist_sync([]) == 0

    def test_invalid_timeframe_noop(self, db, monkeypatch, settings) -> None:
        settings.MARKET_DATA_POLL_TIMEFRAME = "not-a-timeframe"
        monkeypatch.setattr(
            "apps.market_data.infrastructure.polling_tasks.get_market_calendar",
            lambda: FakeCalendar(MarketSession.MARKET_HOURS),
        )
        assert poll_watchlist_sync([("NSE", "RELIANCE")]) == 0

    def test_outside_market_hours_noop(self, db, monkeypatch, settings) -> None:
        settings.MARKET_DATA_POLL_WATCHLIST = [("NSE", "RELIANCE")]
        monkeypatch.setattr(
            "apps.market_data.infrastructure.polling_tasks.get_market_calendar",
            lambda: FakeCalendar(MarketSession.CLOSED),
        )
        _clock(monkeypatch)
        backfill_calls: list[Any] = []

        class Recorder:
            def backfill(self, *args: Any, **kwargs: Any) -> int:
                backfill_calls.append((args, kwargs))
                return 0

        monkeypatch.setattr(
            "apps.market_data.infrastructure.polling_tasks.get_historical_sync_service",
            lambda: Recorder(),
        )

        assert poll_watchlist_sync([("NSE", "RELIANCE")]) == 0
        assert backfill_calls == []


# ---------------------------------------------------------------------------
# sync cycle behaviour
# ---------------------------------------------------------------------------


class TestPollWatchlistSync:
    @pytest.mark.django_db
    def test_poll_persists_candles_and_publishes_ta_snapshot(
        self, db, monkeypatch, settings
    ) -> None:
        from apps.market_data.application.candle_ta_bridge import (
            CandleToTechnicalAnalysisBridge,
        )
        from apps.technical_analysis.infrastructure.models import TASnapshot

        settings.MARKET_DATA_POLL_TIMEFRAME = "1min"
        settings.MARKET_DATA_POLL_WINDOW_SECONDS = 600
        monkeypatch.setattr(
            "apps.market_data.infrastructure.polling_tasks.get_market_calendar",
            lambda: FakeCalendar(MarketSession.MARKET_HOURS),
        )
        _clock(monkeypatch)

        _seed_instrument(1001, "RELIANCE", db)
        _historical_service(monkeypatch, FakeProvider(_bars(Decimal("103.00"))))


        bridge = CandleToTechnicalAnalysisBridge(
            redis_client=FakeRedis(), staleness_seconds=180
        )
        monkeypatch.setattr(
            "apps.market_data.infrastructure.polling_tasks.get_candle_ta_bridge",
            lambda: bridge,
        )

        published = poll_watchlist_sync([("NSE", "RELIANCE")])

        assert published == 1
        assert CandleModel.objects.filter(
            instrument_id=1001, timeframe="1min"
        ).count() == 2
        snapshot = TASnapshot.objects.get(symbol="RELIANCE", timeframe="1min")
        assert snapshot.exchange == "NSE"
        assert Decimal(snapshot.raw_payload["close"]) == Decimal("103.00")
        assert Decimal(snapshot.raw_payload["change_pct"]) == Decimal("2.4876")
        assert "vwap" not in snapshot.raw_payload
        assert "ema_20" not in snapshot.raw_payload

    @pytest.mark.django_db
    def test_unknown_symbol_is_skipped_without_effect(self, db, monkeypatch, settings) -> None:
        settings.MARKET_DATA_POLL_TIMEFRAME = "1min"
        monkeypatch.setattr(
            "apps.market_data.infrastructure.polling_tasks.get_market_calendar",
            lambda: FakeCalendar(MarketSession.MARKET_HOURS),
        )
        _clock(monkeypatch)
        _seed_instrument(2001, "TCS", db)
        _historical_service(monkeypatch, FakeProvider(_bars(Decimal("400.00"))))
        monkeypatch.setattr(
            "apps.market_data.infrastructure.polling_tasks.get_candle_ta_bridge",
            lambda: CandleToTechnicalAnalysisBridge(
                redis_client=FakeRedis(), staleness_seconds=180
            ),
        )

        published = poll_watchlist_sync([("NSE", "MISSING"), ("NSE", "TCS")])

        assert published == 1
        assert CandleModel.objects.filter(instrument_id=2001).count() == 2

    @pytest.mark.django_db
    def test_provider_outage_is_isolated_per_symbol_and_retries(
        self, db, monkeypatch, settings
    ) -> None:
        from apps.technical_analysis.infrastructure.models import TASnapshot

        settings.MARKET_DATA_POLL_TIMEFRAME = "1min"
        monkeypatch.setattr(
            "apps.market_data.infrastructure.polling_tasks.get_market_calendar",
            lambda: FakeCalendar(MarketSession.MARKET_HOURS),
        )
        _clock(monkeypatch)
        _seed_instrument(1001, "RELIANCE", db)
        _seed_instrument(2001, "TCS", db)

        calls: dict[str, int] = {}

        class FailingProvider(FakeProvider):
            def fetch(self, request: Any) -> MarketDataResponse:
                calls[request.symbol] = calls.get(request.symbol, 0) + 1
                if request.symbol == "RELIANCE":
                    raise DataProviderError("provider down")
                return super().fetch(request)

        _historical_service(monkeypatch, FailingProvider(_bars(Decimal("400.00"))))

        monkeypatch.setattr(
            "apps.market_data.infrastructure.polling_tasks.get_candle_ta_bridge",
            lambda: CandleToTechnicalAnalysisBridge(
                redis_client=FakeRedis(), staleness_seconds=180
            ),
        )

        with pytest.raises(DataProviderError, match="provider outage"):
            poll_watchlist_sync([("NSE", "RELIANCE"), ("NSE", "TCS")])

        # The healthy symbol still processed within the same cycle.
        assert TASnapshot.objects.filter(symbol="TCS").count() == 1
        # RELIANCE is attempted on every frame (1D, 15m and the operating 1min
        # under M5.1); the supplementary-frame failures are isolated and only
        # the operating-frame failure surfaces as the provider outage.
        assert calls["RELIANCE"] == 3
        assert calls["TCS"] == 3

    @pytest.mark.django_db
    def test_celery_task_retries_on_provider_outage(self, db, monkeypatch, settings) -> None:
        import celery.exceptions

        settings.MARKET_DATA_POLL_WATCHLIST = [("NSE", "RELIANCE")]
        monkeypatch.setattr(
            "apps.market_data.infrastructure.polling_tasks.poll_watchlist_sync",
            lambda _watchlist: (_ for _ in ()).throw(DataProviderError("down")),
        )

        with pytest.raises(celery.exceptions.Retry):
            poll_market_data_watchlist.apply()


# ---------------------------------------------------------------------------
# Timeframe validity helper (kept as documentation for the allowed set)
# ---------------------------------------------------------------------------


class TestTimeframeContract:
    def test_allowed_poll_timeframes_resolve(self) -> None:
        for value in ("1min", "5min", "15min", "1hr", "1D"):
            assert Timeframe.from_string(value).value == value