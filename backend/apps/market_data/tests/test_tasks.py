"""
Tests for market_data Celery tasks.

``refresh_candles`` must publish exactly one ``marketdata.CandlesPersisted``
event after a successful aggregation + bulk upsert.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

from apps.eventbus.infrastructure.fake_event_bus import FakeEventBus
from apps.market_data.domain.entities import Candle, Instrument
from apps.market_data.infrastructure.tasks import refresh_candles


def _instrument() -> Instrument:
    return Instrument(
        instrument_token=1001,
        exchange="NSE",
        tradingsymbol="RELIANCE",
        name="Reliance Industries Ltd",
        segment="EQUITY",
        lot_size=1,
        tick_size=Decimal("0.05"),
        instrument_type="EQ",
    )


def _candle() -> Candle:
    return Candle(
        instrument_token=1001,
        timeframe="1D",
        timestamp=datetime(2025, 3, 10, 9, 15, tzinfo=timezone.utc),
        open=Decimal(100),
        high=Decimal(105),
        low=Decimal(99),
        close=Decimal(103),
        volume=1000,
    )


class TestRefreshCandles:
    def test_publishes_candles_persisted_after_success(
        self, monkeypatch: Any, db: Any
    ) -> None:
        fake_bus = FakeEventBus()
        monkeypatch.setattr(
            "apps.market_data.infrastructure.tasks.get_event_bus",
            lambda: fake_bus,
        )

        monkeypatch.setattr(
            "apps.market_data.infrastructure.tasks.get_market_data_service",
            lambda: MagicMock(),
        )
        repo = MagicMock()
        repo.bulk_upsert.return_value = 1
        monkeypatch.setattr(
            "apps.market_data.infrastructure.tasks.CandleRepository",
            lambda: repo,
        )
        instrument_repo = MagicMock()
        instrument_repo.find_by_token.return_value = _instrument()
        monkeypatch.setattr(
            "apps.market_data.infrastructure.tasks.InstrumentRepository",
            lambda: instrument_repo,
        )

        provider = MagicMock()
        provider.provider_name = "paper"
        provider.fetch.return_value = MagicMock(bars=())
        monkeypatch.setattr(
            "core.market_data.provider_factory.MarketDataProviderFactory.get_provider",
            lambda: provider,
        )

        aggregator = MagicMock()
        aggregator.aggregate.return_value = [_candle()]
        monkeypatch.setattr(
            "apps.market_data.application.candle_aggregation_service.CandleAggregationService",
            lambda: aggregator,
        )

        result = refresh_candles.apply(args=[1001, "1D"])
        result.get()

        candles_events = [
            e for e in fake_bus.published_events
            if e.event_type == "marketdata.CandlesPersisted"
        ]
        assert len(candles_events) == 1
        event = candles_events[0]
        assert event.payload["instrument_token"] == 1001
        assert event.payload["timeframe"] == "1D"
        assert event.payload["candle_count"] == 1
        assert event.payload["provider"] == "paper"
