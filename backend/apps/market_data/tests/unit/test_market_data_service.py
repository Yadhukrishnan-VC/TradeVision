from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.common.domain.value_objects import Symbol
from apps.market_data.application.market_data_service import MarketDataService
from apps.market_data.domain.entities import Candle, Instrument, Quote
from apps.market_data.domain.value_objects import Timeframe
from apps.market_data.infrastructure.cache import CandleCache, QuoteCache
from apps.market_data.infrastructure.repositories import CandleRepository, InstrumentRepository


class TestMarketDataService:
    @pytest.fixture
    def instrument(self) -> Instrument:
        return Instrument(
            instrument_token=1001,
            exchange="NSE",
            tradingsymbol="RELIANCE",
            name="Reliance Industries Ltd",
            segment="EQUITY",
            lot_size=1,
            tick_size=Decimal("0.05"),
            instrument_type="EQ",
            is_active=True,
        )

    @pytest.fixture
    def symbol(self) -> Symbol:
        return Symbol(exchange="NSE", tradingsymbol="RELIANCE")

    @pytest.fixture
    def mock_quote_cache(self) -> MagicMock:
        return MagicMock(spec=QuoteCache)

    @pytest.fixture
    def mock_candle_cache(self) -> MagicMock:
        return MagicMock(spec=CandleCache)

    @pytest.fixture
    def mock_instrument_repo(self) -> MagicMock:
        return MagicMock(spec=InstrumentRepository)

    @pytest.fixture
    def mock_candle_repo(self) -> MagicMock:
        return MagicMock(spec=CandleRepository)

    @pytest.fixture
    def service(
        self,
        mock_quote_cache: MagicMock,
        mock_candle_cache: MagicMock,
        mock_instrument_repo: MagicMock,
        mock_candle_repo: MagicMock,
    ) -> MarketDataService:
        return MarketDataService(
            instrument_repository=mock_instrument_repo,
            candle_repository=mock_candle_repo,
            quote_cache=mock_quote_cache,
            candle_cache=mock_candle_cache,
        )

    def test_get_quote_from_cache(
        self,
        service: MarketDataService,
        mock_quote_cache: MagicMock,
        symbol: Symbol,
    ) -> None:
        expected_quote = Quote(
            symbol="NSE:RELIANCE",
            ltp=Decimal("2500.00"),
            volume=100000,
            tick_at=datetime(2025, 3, 10, 10, 0, tzinfo=timezone.utc),
        )
        mock_quote_cache.get.return_value = expected_quote

        quote = service.get_quote(symbol)
        assert quote.ltp == expected_quote.ltp
        mock_quote_cache.get.assert_called_once_with(symbol)

    def test_get_quote_unknown_symbol(
        self,
        service: MarketDataService,
        mock_quote_cache: MagicMock,
        mock_instrument_repo: MagicMock,
        symbol: Symbol,
    ) -> None:
        mock_quote_cache.get.return_value = None
        mock_instrument_repo.find_by_symbol.return_value = None

        with pytest.raises(Exception, match="Instrument not found"):
            service.get_quote(symbol)

    def test_get_market_session(self, service: MarketDataService) -> None:
        from core.market_calendar import MarketSession

        session = service.get_market_session()
        assert isinstance(session, MarketSession) or session is not None

    def test_is_market_open(self, service: MarketDataService) -> None:
        result = service.is_market_open()
        assert isinstance(result, bool)

    def test_get_candles_from_cache(
        self,
        service: MarketDataService,
        mock_candle_cache: MagicMock,
        symbol: Symbol,
    ) -> None:
        expected = [
            Candle(
                instrument_token=1001,
                timeframe="15min",
                timestamp=datetime(2025, 3, 10, 9, 15, tzinfo=timezone.utc),
                open=Decimal("100"),
                high=Decimal("105"),
                low=Decimal("99"),
                close=Decimal("103"),
                volume=50000,
            ),
        ]
        mock_candle_cache.get.return_value = expected

        candles = service.get_candles(symbol, Timeframe.MINUTE_15, lookback=1)
        assert len(candles) == 1
        assert candles[0].close == Decimal("103")

    def test_get_candles_unknown_symbol(
        self,
        service: MarketDataService,
        mock_candle_cache: MagicMock,
        mock_instrument_repo: MagicMock,
        symbol: Symbol,
    ) -> None:
        mock_candle_cache.get.return_value = None
        mock_instrument_repo.find_by_symbol.return_value = None

        with pytest.raises(Exception, match="Instrument not found"):
            service.get_candles(symbol, Timeframe.MINUTE_15, lookback=50)
