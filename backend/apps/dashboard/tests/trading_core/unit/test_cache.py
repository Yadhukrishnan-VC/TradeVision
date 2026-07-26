from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from apps.dashboard.infrastructure.trading_core.cache import (
    DashboardHomeCache,
    DecimalEncoder,
    LatestPriceCache,
    PortfolioDebounceCache,
    PositionDebounceCache,
)


class TestLatestPriceCache:
    def test_set_and_get_price(self) -> None:
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {"price": "2600.00"}
        cache = LatestPriceCache(redis_client=mock_redis)

        cache.set_price("RELIANCE", Decimal("2600.00"))
        price = cache.get_price("RELIANCE")

        assert price == Decimal("2600.00")

    def test_get_price_not_found(self) -> None:
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {}
        cache = LatestPriceCache(redis_client=mock_redis)

        price = cache.get_price("UNKNOWN")
        assert price is None


class TestDashboardHomeCache:
    def test_set_and_get_summary(self) -> None:
        account_id = uuid.uuid4()
        mock_redis = MagicMock()
        mock_redis.get.return_value = '{"open_positions_count": 5}'
        cache = DashboardHomeCache(redis_client=mock_redis)

        data = cache.get_summary(account_id)
        assert data is not None
        assert data["open_positions_count"] == 5

    def test_get_summary_not_found(self) -> None:
        account_id = uuid.uuid4()
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        cache = DashboardHomeCache(redis_client=mock_redis)

        data = cache.get_summary(account_id)
        assert data is None


class TestDebounceCaches:
    def test_portfolio_debounce(self) -> None:
        account_id = uuid.uuid4()
        mock_redis = MagicMock()
        mock_redis.exists.return_value = 1
        cache = PortfolioDebounceCache(redis_client=mock_redis)

        assert cache.is_debounced(account_id) is True

    def test_portfolio_not_debounced(self) -> None:
        account_id = uuid.uuid4()
        mock_redis = MagicMock()
        mock_redis.exists.return_value = 0
        cache = PortfolioDebounceCache(redis_client=mock_redis)

        assert cache.is_debounced(account_id) is False

    def test_position_debounce(self) -> None:
        account_id = uuid.uuid4()
        position_id = uuid.uuid4()
        mock_redis = MagicMock()
        mock_redis.exists.return_value = 1
        cache = PositionDebounceCache(redis_client=mock_redis)

        assert cache.is_debounced(account_id, position_id) is True


class TestDecimalEncoder:
    def test_encodes_decimal(self) -> None:
        encoder = DecimalEncoder()
        result = encoder.default(Decimal("123.45"))
        assert result == "123.45"

    def test_encodes_uuid(self) -> None:
        uid = uuid.uuid4()
        encoder = DecimalEncoder()
        result = encoder.default(uid)
        assert result == str(uid)

    def test_raises_on_unknown_type(self) -> None:
        encoder = DecimalEncoder()
        with pytest.raises(TypeError):
            encoder.default(object())
