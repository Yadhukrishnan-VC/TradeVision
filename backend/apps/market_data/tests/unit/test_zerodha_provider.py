from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.market_data.infrastructure.providers.zerodha_provider import (
    ZerodhaMarketDataProvider,
)
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
