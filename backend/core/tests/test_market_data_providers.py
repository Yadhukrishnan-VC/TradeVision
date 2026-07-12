"""
Tests for market data providers — MockProvider contract, factory singleton, reset.
"""

import pytest

from core.market_data.base_provider import BaseMarketDataProvider, MarketDataRequest
from core.market_data.providers.mock_provider import MockMarketDataProvider
from core.market_data.provider_factory import MarketDataProviderFactory


class TestMockMarketDataProvider:

    def test_provider_name(self) -> None:
        p = MockMarketDataProvider()
        assert p.provider_name == "mock"

    def test_validate_connection(self) -> None:
        p = MockMarketDataProvider()
        assert p.validate_connection() is True

    def test_health_check(self) -> None:
        p = MockMarketDataProvider()
        status = p.health_check()
        assert status["status"] == "healthy"

    def test_fetch_returns_deterministic_data(self) -> None:
        p = MockMarketDataProvider()
        request = MarketDataRequest(symbol="RELIANCE")
        response = p.fetch(request)
        assert response.provider == "mock"
        assert response.symbol == "RELIANCE"
        assert len(response.data_points) == 1

    def test_close_does_not_raise(self) -> None:
        p = MockMarketDataProvider()
        p.close()

    def test_is_subclass(self) -> None:
        assert issubclass(MockMarketDataProvider, BaseMarketDataProvider)


class TestMarketDataProviderFactory:

    def setup_method(self) -> None:
        MarketDataProviderFactory.reset()

    def teardown_method(self) -> None:
        MarketDataProviderFactory.reset()

    def test_returns_same_instance(self) -> None:
        p1 = MarketDataProviderFactory.get_provider()
        p2 = MarketDataProviderFactory.get_provider()
        assert p1 is p2

    def test_reset_clears_instance(self) -> None:
        p1 = MarketDataProviderFactory.get_provider()
        MarketDataProviderFactory.reset()
        p2 = MarketDataProviderFactory.get_provider()
        assert p1 is not p2

    def test_returns_mock_provider(self) -> None:
        provider = MarketDataProviderFactory.get_provider()
        assert provider.provider_name == "mock"
