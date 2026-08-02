"""
End-to-end-ish activation tests for the market data provider factory.

Exercises real objects (real ``MarketDataProviderFactory`` singleton, real
``PaperMarketDataProvider``, real ``ZerodhaMarketDataProvider`` with mocked
HTTP) through ``override_settings`` so provider selection is proven at the
configuration boundary, not just via direct class instantiation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import override_settings

from apps.market_data.infrastructure.providers.paper_provider import (
    PaperMarketDataProvider,
)
from apps.market_data.infrastructure.providers.zerodha_provider import (
    ZerodhaMarketDataProvider,
)
from core.market_data.base_provider import MarketDataRequest
from core.market_data.provider_factory import MarketDataProviderFactory


def _make_request(symbol: str = "RELIANCE") -> MarketDataRequest:
    now = datetime(2025, 3, 10, 9, 15, tzinfo=timezone.utc)
    return MarketDataRequest(
        symbol=symbol,
        interval="15min",
        from_timestamp=now,
        to_timestamp=now + timedelta(hours=2),
    )


class TestPaperProviderActivation:
    def test_factory_selects_paper_and_fetches_deterministically(self) -> None:
        MarketDataProviderFactory.reset()
        try:
            with override_settings(MARKET_DATA_PROVIDER="paper"):
                provider = MarketDataProviderFactory.get_provider()
            assert isinstance(provider, PaperMarketDataProvider)
            assert provider.provider_name == "paper"
            assert provider.validate_connection() is True

            request = _make_request()
            response1 = provider.fetch(request)
            response2 = provider.fetch(request)

            assert response1.provider == "paper"
            assert response1.bar_count > 0
            assert response1.bars == response2.bars
            for bar in response1.bars:
                assert bar.high >= bar.low
                assert bar.volume >= 0
        finally:
            MarketDataProviderFactory.reset()


class TestZerodhaProviderActivation:
    def test_factory_selects_zerodha(self) -> None:
        MarketDataProviderFactory.reset()
        try:
            with override_settings(MARKET_DATA_PROVIDER="zerodha"):
                provider = MarketDataProviderFactory.get_provider()
            assert isinstance(provider, ZerodhaMarketDataProvider)
            assert provider.provider_name == "zerodha"
        finally:
            MarketDataProviderFactory.reset()

    @patch("apps.market_data.infrastructure.providers.zerodha_provider.requests")
    def test_validate_connection_mocked(self, mock_requests: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_requests.get.return_value = mock_response

        provider = ZerodhaMarketDataProvider()
        assert provider.validate_connection() is True

    @patch(
        "apps.market_data.infrastructure.repositories.InstrumentRepository.find_by_symbol"
    )
    @patch("apps.market_data.infrastructure.providers.zerodha_provider.requests.Session")
    def test_fetch_mocked_http_with_resolved_token(
        self,
        mock_session_cls: MagicMock,
        mock_find_by_symbol: MagicMock,
    ) -> None:
        from apps.market_data.domain.entities import Instrument

        mock_find_by_symbol.return_value = Instrument(
            instrument_token=256265,
            exchange="NSE",
            tradingsymbol="TCS",
            name="Tata Consultancy Services Ltd",
            segment="EQUITY",
            lot_size=1,
            tick_size=Decimal("0.05"),
            instrument_type="EQ",
        )

        mock_session = mock_session_cls.return_value
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "candles": [
                    ["2025-03-10T09:15:00+05:30", 100, 105, 99, 103, 50000],
                ]
            },
        }
        mock_session.get.return_value = mock_response

        provider = ZerodhaMarketDataProvider()
        response = provider.fetch(_make_request(symbol="TCS"))

        url = mock_session.get.call_args.args[0]
        assert "/instruments/historical/256265/15minute" in url
        assert response.provider == "zerodha"
        assert response.bar_count == 1

    @patch("apps.market_data.infrastructure.providers.zerodha_provider.requests.Session")
    def test_fetch_instruments_mocked(self, mock_session_cls: MagicMock) -> None:
        mock_session = mock_session_cls.return_value
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            {
                "instrument_token": 256265,
                "exchange": "NSE",
                "tradingsymbol": "TCS",
                "name": "Tata Consultancy Services Ltd",
                "segment": "EQUITY",
                "lot_size": 1,
                "tick_size": "0.05",
                "instrument_type": "EQ",
                "expiry": None,
            }
        ]
        mock_session.get.return_value = mock_response

        provider = ZerodhaMarketDataProvider()
        instruments = provider.fetch_instruments()
        assert instruments[0]["instrument_token"] == 256265
        assert instruments[0]["tradingsymbol"] == "TCS"
