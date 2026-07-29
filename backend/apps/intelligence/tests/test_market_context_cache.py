from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.intelligence.domain.market_regime import MarketRegime, MultiTimeframeAlignment
from apps.intelligence.infrastructure.market_context_cache import MarketContextCache
from apps.intelligence.services import SignalContext
from core.events.event_types import PatternContext, PatternMatch


def _sample_context() -> SignalContext:
    return SignalContext(
        symbol="RELIANCE",
        timestamp=datetime.now(timezone.utc),
        market_regime=MarketRegime.BULLISH,
        multi_timeframe_alignment=MultiTimeframeAlignment.BULLISH_ALIGNED,
        bullishness_score=0.74,
        bearishness_score=0.11,
        volatility_score=0.32,
        trend_score=0.68,
        liquidity_score=0.81,
        momentum_score=0.63,
        overall_context_confidence=0.88,
        pattern_alignment_note="PATTERN_ENGINE_NOT_AVAILABLE",
    )


class TestMarketContextCache:
    def test_set_and_get_round_trips(self) -> None:
        mock_redis = MagicMock()
        context = _sample_context()

        cache = MarketContextCache(redis_client=mock_redis)
        cache.set("RELIANCE", context, ttl_seconds=300)

        mock_redis.setex.assert_called_once()
        args, kwargs = mock_redis.setex.call_args
        assert args[0] == "market_context:RELIANCE"
        assert args[1] == 300
        stored_data = json.loads(args[2])
        assert stored_data["symbol"] == "RELIANCE"
        assert stored_data["bullishness_score"] == 0.74

    def test_get_returns_none_for_missing_key(self) -> None:
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        cache = MarketContextCache(redis_client=mock_redis)
        result = cache.get("UNKNOWN")
        assert result is None

    def test_get_returns_context_for_existing_key(self) -> None:
        mock_redis = MagicMock()
        ctx = _sample_context()
        from core.events.event_bus import _EventEncoder
        import dataclasses

        serialized = json.dumps(dataclasses.asdict(ctx), cls=_EventEncoder)
        mock_redis.get.return_value = serialized

        cache = MarketContextCache(redis_client=mock_redis)
        result = cache.get("RELIANCE")
        assert result is not None
        assert result.symbol == "RELIANCE"
        assert result.bullishness_score == 0.74
        assert result.market_regime == MarketRegime.BULLISH
        assert result.pattern_alignment_note == "PATTERN_ENGINE_NOT_AVAILABLE"

    def test_get_handles_redis_exception_gracefully(self) -> None:
        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("Redis down")

        cache = MarketContextCache(redis_client=mock_redis)
        result = cache.get("RELIANCE")
        assert result is None

    def test_set_handles_redis_exception_gracefully(self) -> None:
        mock_redis = MagicMock()
        mock_redis.setex.side_effect = Exception("Redis down")

        cache = MarketContextCache(redis_client=mock_redis)
        cache.set("RELIANCE", _sample_context())
        assert True

    def test_attach_pattern_context_on_existing_entry(self) -> None:
        import dataclasses
        from core.events.event_bus import _EventEncoder

        mock_redis = MagicMock()
        ctx = _sample_context()
        serialized = json.dumps(dataclasses.asdict(ctx), cls=_EventEncoder)
        mock_redis.get.return_value = serialized
        mock_redis.ttl.return_value = 500

        cache = MarketContextCache(redis_client=mock_redis)
        pattern_ctx = PatternContext(
            similar_dates=(
                PatternMatch(
                    date_str="2024-03-17",
                    similarity_score=Decimal("0.85"),
                    outcome_summary="Price rose 2%",
                ),
            ),
            top_analogue_summary="Similar to 2024-03-17: price rose 2%",
        )
        cache.attach_pattern_context("RELIANCE", pattern_ctx)

        assert mock_redis.setex.called
        args, kwargs = mock_redis.setex.call_args
        stored_data = json.loads(args[2])
        assert stored_data["pattern_alignment_note"] == "Similar to 2024-03-17: price rose 2%"

    def test_attach_pattern_context_on_missing_entry_is_noop(self) -> None:
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        cache = MarketContextCache(redis_client=mock_redis)
        pattern_ctx = PatternContext(top_analogue_summary="Test")
        cache.attach_pattern_context("UNKNOWN", pattern_ctx)
        assert not mock_redis.setex.called

    def test_get_with_decimal_and_enum_fields_restored(self) -> None:
        import dataclasses
        from core.events.event_bus import _EventEncoder

        mock_redis = MagicMock()
        ctx = _sample_context()
        serialized = json.dumps(dataclasses.asdict(ctx), cls=_EventEncoder)
        mock_redis.get.return_value = serialized

        cache = MarketContextCache(redis_client=mock_redis)
        result = cache.get("RELIANCE")
        assert result.market_regime == MarketRegime.BULLISH
        assert result.multi_timeframe_alignment == MultiTimeframeAlignment.BULLISH_ALIGNED
        assert result.overall_context_confidence == 0.88
