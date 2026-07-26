from __future__ import annotations

"""Parametrized contract tests for all market data providers.

Every provider registered in ``MarketDataProviderFactory`` must satisfy
the same contract. These tests validate that contract for every provider
in the ``provider_map``.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from core.exceptions import DataProviderError
from core.market_data.base_provider import (
    BaseMarketDataProvider,
    MarketDataRequest,
)
from core.market_data.provider_factory import MarketDataProviderFactory

_PROVIDER_NAMES: list[str] = ["mock", "paper"]


@pytest.mark.parametrize("provider_name", _PROVIDER_NAMES)
class TestMarketDataProviderContract:
    """Contract tests that every provider must pass.

    These tests validate the abstract interface defined by
    ``BaseMarketDataProvider`` without assuming any provider-specific
    behaviour.
    """

    def _get_provider(self, provider_name: str) -> BaseMarketDataProvider:
        """Construct a provider instance.

        We bypass the factory's singleton to test each provider
        independently.
        """
        from core.config import config

        if provider_name == "mock":
            from core.market_data.providers.mock_provider import MockMarketDataProvider

            return MockMarketDataProvider()
        elif provider_name == "paper":
            from apps.market_data.infrastructure.providers.paper_provider import (
                PaperMarketDataProvider,
            )

            return PaperMarketDataProvider()
        else:
            raise ValueError(f"Unknown provider: {provider_name}")

    def test_provider_name_is_set(self, provider_name: str) -> None:
        provider = self._get_provider(provider_name)
        assert provider.provider_name
        assert isinstance(provider.provider_name, str)

    def test_validate_connection(self, provider_name: str) -> None:
        provider = self._get_provider(provider_name)
        result = provider.validate_connection()
        assert result is True

    def test_health_check_returns_required_fields(self, provider_name: str) -> None:
        provider = self._get_provider(provider_name)
        result = provider.health_check()

        assert "status" in result
        assert result["status"] in ("healthy", "degraded", "unhealthy")
        assert "provider" in result
        assert result["provider"] == provider_name
        assert "latency_ms" in result

    def test_fetch_returns_market_data_response(self, provider_name: str) -> None:
        provider = self._get_provider(provider_name)
        now = datetime(2025, 3, 10, 9, 15, tzinfo=timezone.utc)

        request = MarketDataRequest(
            symbol="RELIANCE",
            interval="15min",
            from_timestamp=now,
            to_timestamp=now + timedelta(hours=2),
        )

        response = provider.fetch(request)

        assert response.symbol == "RELIANCE"
        assert response.interval == "15min"
        assert response.provider == provider_name
        assert len(response.bars) > 0

        for bar in response.bars:
            assert bar.high >= bar.low
            assert bar.volume >= 0

    def test_fetch_returns_chronological_bars(self, provider_name: str) -> None:
        provider = self._get_provider(provider_name)
        now = datetime(2025, 3, 10, 9, 15, tzinfo=timezone.utc)

        request = MarketDataRequest(
            symbol="TCS",
            interval="1min",
            from_timestamp=now,
            to_timestamp=now + timedelta(hours=1),
        )

        response = provider.fetch(request)
        timestamps = [bar.timestamp for bar in response.bars]
        assert timestamps == sorted(timestamps)

    def test_close_does_not_raise(self, provider_name: str) -> None:
        provider = self._get_provider(provider_name)
        provider.close()

    def test_deterministic_fetch(self, provider_name: str) -> None:
        provider = self._get_provider(provider_name)
        now = datetime(2025, 3, 10, 9, 15, tzinfo=timezone.utc)

        request = MarketDataRequest(
            symbol="RELIANCE",
            interval="15min",
            from_timestamp=now,
            to_timestamp=now + timedelta(hours=2),
        )

        response1 = provider.fetch(request)
        response2 = provider.fetch(request)

        assert len(response1.bars) == len(response2.bars)

    def test_fetch_with_different_symbols(self, provider_name: str) -> None:
        provider = self._get_provider(provider_name)
        now = datetime(2025, 3, 10, 9, 15, tzinfo=timezone.utc)

        req1 = MarketDataRequest(
            symbol="RELIANCE",
            interval="15min",
            from_timestamp=now,
            to_timestamp=now + timedelta(hours=1),
        )
        req2 = MarketDataRequest(
            symbol="TCS",
            interval="15min",
            from_timestamp=now,
            to_timestamp=now + timedelta(hours=1),
        )

        resp1 = provider.fetch(req1)
        resp2 = provider.fetch(req2)

        if provider_name in ("mock", "paper"):
            assert resp1.bars[0].open_price != resp2.bars[0].open_price
