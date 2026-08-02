from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.market_data.domain.entities import Instrument
from apps.market_data.infrastructure.providers.zerodha_provider import (
    ZerodhaMarketDataProvider,
)
from core.exceptions import DataProviderError
from core.market_data.base_provider import MarketDataRequest


class TestZerodhaMarketDataProvider:
    def test_provider_name(self) -> None:
        provider = ZerodhaMarketDataProvider()
        assert provider.provider_name == "zerodha"

    def test_map_interval(self) -> None:
        assert ZerodhaMarketDataProvider._map_interval("1min") == "minute"
        assert ZerodhaMarketDataProvider._map_interval("15min") == "15minute"
        assert ZerodhaMarketDataProvider._map_interval("1hr") == "60minute"
        assert ZerodhaMarketDataProvider._map_interval("1D") == "day"

    def test_map_interval_invalid(self) -> None:
        with pytest.raises(Exception):
            ZerodhaMarketDataProvider._map_interval("invalid")

    @patch("apps.market_data.infrastructure.providers.zerodha_provider.requests")
    def test_validate_connection_success(self, mock_requests: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_requests.get.return_value = mock_response

        provider = ZerodhaMarketDataProvider()
        result = provider.validate_connection()
        assert result is True

    @patch("apps.market_data.infrastructure.providers.zerodha_provider.requests")
    def test_validate_connection_failure(self, mock_requests: MagicMock) -> None:
        from requests.exceptions import RequestException

        mock_requests.get.side_effect = RequestException("Connection error")

        provider = ZerodhaMarketDataProvider()
        with pytest.raises(Exception):
            provider.validate_connection()

    def test_health_check_offline(self) -> None:
        provider = ZerodhaMarketDataProvider()
        with patch.object(provider, "validate_connection", return_value=True):
            result = provider.health_check()
            assert result["status"] == "healthy"
            assert result["provider"] == "zerodha"

    def _make_request(self, symbol: str = "RELIANCE") -> MarketDataRequest:
        now = datetime(2025, 3, 10, 9, 15, tzinfo=timezone.utc)
        return MarketDataRequest(
            symbol=symbol,
            interval="1D",
            from_timestamp=now,
            to_timestamp=now + timedelta(days=1),
        )

    @patch(
        "apps.market_data.infrastructure.repositories.InstrumentRepository.find_by_symbol"
    )
    @patch("apps.market_data.infrastructure.providers.zerodha_provider.requests.Session")
    def test_fetch_uses_instrument_token_not_symbol(
        self,
        mock_session_cls: MagicMock,
        mock_find_by_symbol: MagicMock,
    ) -> None:
        mock_instrument = Instrument(
            instrument_token=738561,
            exchange="NSE",
            tradingsymbol="RELIANCE",
            name="Reliance Industries Ltd",
            segment="EQUITY",
            lot_size=1,
            tick_size=Decimal("0.05"),
            instrument_type="EQ",
        )
        mock_find_by_symbol.return_value = mock_instrument

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
        response = provider.fetch(self._make_request())

        url = mock_session.get.call_args.args[0]
        assert "/instruments/historical/738561/day" in url
        assert "RELIANCE" not in url
        assert response.bar_count == 1

    @patch(
        "apps.market_data.infrastructure.repositories.InstrumentRepository.find_by_symbol",
        return_value=None,
    )
    def test_fetch_raises_when_instrument_unresolved(
        self,
        mock_find_by_symbol: MagicMock,
    ) -> None:
        provider = ZerodhaMarketDataProvider()
        with pytest.raises(DataProviderError, match="instrument"):
            provider.fetch(self._make_request())
