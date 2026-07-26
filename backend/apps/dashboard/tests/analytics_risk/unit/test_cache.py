from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from apps.dashboard.infrastructure.analytics_risk.cache import (
    PerformanceCache,
    PnLWebSocketDebounceCache,
    RiskDebounceCache,
    RiskLatestCache,
)


class TestRiskLatestCache:
    def test_set_and_get(self) -> None:
        mock_redis = MagicMock()
        mock_redis.get.return_value = b'{"total_exposure": "5000"}'

        cache = RiskLatestCache(redis_client=mock_redis)
        result = cache.get_snapshot(uuid4())

        assert result is not None
        assert result["total_exposure"] == "5000"

    def test_get_miss(self) -> None:
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        cache = RiskLatestCache(redis_client=mock_redis)
        result = cache.get_snapshot(uuid4())

        assert result is None

    def test_delete(self) -> None:
        mock_redis = MagicMock()
        cache = RiskLatestCache(redis_client=mock_redis)
        cache.delete_snapshot(uuid4())
        mock_redis.delete.assert_called_once()


class TestPerformanceCache:
    def test_set_and_get(self) -> None:
        mock_redis = MagicMock()
        mock_redis.get.return_value = b'{"win_rate": "0.5"}'

        cache = PerformanceCache(redis_client=mock_redis)
        result = cache.get_metrics(uuid4(), "30d")

        assert result is not None
        assert result["win_rate"] == "0.5"

    def test_delete(self) -> None:
        mock_redis = MagicMock()
        cache = PerformanceCache(redis_client=mock_redis)
        cache.delete_metrics(uuid4(), "30d")
        mock_redis.delete.assert_called_once()


class TestPnlWebSocketDebounceCache:
    def test_is_debounced(self) -> None:
        mock_redis = MagicMock()
        mock_redis.exists.return_value = 1

        cache = PnLWebSocketDebounceCache(redis_client=mock_redis)
        assert cache.is_debounced(uuid4()) is True

    def test_not_debounced(self) -> None:
        mock_redis = MagicMock()
        mock_redis.exists.return_value = 0

        cache = PnLWebSocketDebounceCache(redis_client=mock_redis)
        assert cache.is_debounced(uuid4()) is False

    def test_mark(self) -> None:
        mock_redis = MagicMock()
        cache = PnLWebSocketDebounceCache(redis_client=mock_redis)
        cache.mark(uuid4())
        mock_redis.setex.assert_called_once()


class TestRiskDebounceCache:
    def test_is_debounced(self) -> None:
        mock_redis = MagicMock()
        mock_redis.exists.return_value = 1

        cache = RiskDebounceCache(redis_client=mock_redis)
        assert cache.is_debounced(uuid4()) is True
