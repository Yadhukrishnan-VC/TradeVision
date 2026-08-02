"""
Integration test for ``marketdata.CandlesPersisted`` event publication.

``HistoricalSyncService.backfill`` persists candles AND publishes exactly one
``marketdata.CandlesPersisted`` event per successful run. Persistence and
event publication are asserted independently (two separate assertions), using
a real ``FakeEventBus`` (the real in-memory EventBus implementation) and a
stubbed provider + recording candle repository so the actual data path
(persist → publish) is exercised rather than mocked end-to-end.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest

from apps.eventbus.infrastructure.fake_event_bus import FakeEventBus
from apps.market_data.application.historical_sync_service import HistoricalSyncService
from apps.market_data.domain.entities import Instrument
from apps.market_data.domain.value_objects import Timeframe
from core.market_data.base_provider import OHLCVBar


class RecordingCandleRepo:
    """In-memory candle repo that records every upsert call."""

    def __init__(self) -> None:
        self.upserted: list[dict[str, Any]] = []

    def upsert(self, **kwargs: Any) -> None:
        self.upserted.append(kwargs)


class StubProvider:
    provider_name = "paper"

    def __init__(self, bars: list[OHLCVBar]) -> None:
        self._bars = bars

    def fetch(self, request: Any) -> Any:
        from core.market_data.base_provider import MarketDataResponse
        from core.utils import get_now

        return MarketDataResponse(
            request_id=request.request_id or "",
            symbol=request.symbol,
            interval=request.interval,
            bars=tuple(self._bars),
            provider=self.provider_name,
            fetched_at=get_now(),
            is_complete=True,
            meta={"paper": True},
        )


def _make_bars(n: int = 3) -> list[OHLCVBar]:
    start = datetime(2025, 3, 10, 9, 15, tzinfo=timezone.utc)
    return [
        OHLCVBar(
            timestamp=start + timedelta(minutes=i * 15),
            open_price=Decimal(100),
            high=Decimal(105),
            low=Decimal(99),
            close_price=Decimal(103),
            volume=1000 * (i + 1),
        )
        for i in range(n)
    ]


@pytest.mark.django_db
class TestHistoricalSyncEventPublication:
    def _make_service(
        self,
        fake_bus: FakeEventBus,
    ) -> tuple[HistoricalSyncService, RecordingCandleRepo]:
        instrument = Instrument(
            instrument_token=1001,
            exchange="NSE",
            tradingsymbol="RELIANCE",
            name="Reliance Industries Ltd",
            segment="EQUITY",
            lot_size=1,
            tick_size=Decimal("0.05"),
            instrument_type="EQ",
        )
        instrument_repo = MagicMock()
        instrument_repo.find_by_token.return_value = instrument
        candle_repo = RecordingCandleRepo()

        breaker = MagicMock()
        breaker.call.side_effect = lambda func, *args, **kwargs: func(*args, **kwargs)

        service = HistoricalSyncService(
            instrument_repo=instrument_repo,
            candle_repo=candle_repo,
        )
        service._circuit_factory = MagicMock()
        service._circuit_factory.get_or_create.return_value = breaker
        return service, candle_repo

    def test_backfill_persists_and_publishes_one_event(
        self, monkeypatch: Any
    ) -> None:
        fake_bus = FakeEventBus()
        monkeypatch.setattr(
            "apps.eventbus.infrastructure.event_bus_factory.get_event_bus",
            lambda: fake_bus,
        )
        service, candle_repo = self._make_service(fake_bus)

        provider = StubProvider(_make_bars())
        monkeypatch.setattr(
            "apps.market_data.application.historical_sync_service.MarketDataProviderFactory.get_provider",
            lambda: provider,
        )

        persisted = service.backfill(
            instrument_token=1001,
            timeframe=Timeframe.DAY_1,
            from_timestamp=datetime(2025, 3, 10, 9, 15, tzinfo=timezone.utc),
            to_timestamp=datetime(2025, 3, 10, 9, 45, tzinfo=timezone.utc),
        )

        assert persisted == 3
        assert len(candle_repo.upserted) == 3

        candles_events = [
            e for e in fake_bus.published_events
            if e.event_type == "marketdata.CandlesPersisted"
        ]
        assert len(candles_events) == 1
        event = candles_events[0]
        assert event.payload["instrument_token"] == 1001
        assert event.payload["timeframe"] == "1D"
        assert event.payload["candle_count"] == 3
        assert event.payload["provider"] == "paper"

    def test_backfill_publishes_event_with_zero_count_when_no_bars(
        self, monkeypatch: Any
    ) -> None:
        fake_bus = FakeEventBus()
        monkeypatch.setattr(
            "apps.eventbus.infrastructure.event_bus_factory.get_event_bus",
            lambda: fake_bus,
        )
        service, candle_repo = self._make_service(fake_bus)

        provider = StubProvider([])
        monkeypatch.setattr(
            "apps.market_data.application.historical_sync_service.MarketDataProviderFactory.get_provider",
            lambda: provider,
        )

        persisted = service.backfill(
            instrument_token=1001,
            timeframe=Timeframe.DAY_1,
            from_timestamp=datetime(2025, 3, 10, 9, 15, tzinfo=timezone.utc),
            to_timestamp=datetime(2025, 3, 10, 9, 45, tzinfo=timezone.utc),
        )

        assert persisted == 0
        assert candle_repo.upserted == []

        candles_events = [
            e for e in fake_bus.published_events
            if e.event_type == "marketdata.CandlesPersisted"
        ]
        assert len(candles_events) == 1
        assert candles_events[0].payload["candle_count"] == 0
