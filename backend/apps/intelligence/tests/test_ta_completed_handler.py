from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.intelligence.infrastructure.ta_completed_handler import (
    NEWS_MISSING_QUALITY_PENALTY,
    _build_packet,
    _detect_regime_value,
    _get_prev_close,
    _optional_decimal,
    handle_ta_completed,
)
from core.events.event_types import (
    AggregateSentiment,
    MaterialityLevel,
    NewsContext,
    NewsItem,
)


class _EmptyNewsLookup:
    """NewsContextService stand-in: a real lookup that finds no headlines."""

    def build(self, symbol: str, *, as_of=None) -> tuple[NewsContext, bool]:
        return NewsContext(), True


class _PopulatedNewsLookup:
    """NewsContextService stand-in: a lookup that finds headlines."""

    def build(self, symbol: str, *, as_of=None) -> tuple[NewsContext, bool]:
        context = NewsContext(
            headlines=(
                NewsItem(
                    title="RELIANCE Q2 profit beats estimates",
                    source="Reuters",
                    sentiment=AggregateSentiment.POSITIVE,
                    materiality=MaterialityLevel.LOW,
                    age_minutes=5,
                    url="https://example.com/news/1",
                ),
            ),
            aggregate_sentiment=AggregateSentiment.POSITIVE,
        )
        return context, True


@pytest.fixture(autouse=True)
def _hermetic_news_lookup(monkeypatch) -> None:
    """Keep news lookups deterministic (empty) across the module's tests.

    The batch's bridge integration test overrides this per-test where a
    populated news context is exercised.
    """
    from apps.intelligence.infrastructure import ta_completed_handler

    monkeypatch.setattr(
        ta_completed_handler, "get_news_context_service", lambda: _EmptyNewsLookup()
    )


class TestHandleTACompleted:
    def test_missing_symbol_logs_warning(self) -> None:
        event = DomainEvent.create(
            event_type="technical_analysis.TechnicalAnalysisCompleted",
            payload={},
            correlation_id=uuid.uuid4(),
        )
        handle_ta_completed(event)

    def test_publishes_packet_enriched_for_valid_payload(self) -> None:
        cid = uuid.uuid4()
        event = DomainEvent.create(
            event_type="technical_analysis.TechnicalAnalysisCompleted",
            payload={
                "symbol": "RELIANCE",
                "snapshot_id": "snap-123",
                "exchange": "NSE",
                "timeframe": "1D",
                "snapshot_timestamp": "2026-07-28T10:00:00+00:00",
                "indicators": {"rsi_14": 62.5, "macd": 1.23},
                "price": {"close": "3124.50", "high": "3145.00"},
                "pine_id": "test_script",
                "pine_version": "5",
            },
            correlation_id=cid,
        )

        with patch("apps.intelligence.infrastructure.ta_completed_handler.get_event_bus") as mock_get_bus:
            mock_bus = MagicMock()
            mock_get_bus.return_value = mock_bus

            handle_ta_completed(event)

            assert mock_bus.publish.called
            published_event = mock_bus.publish.call_args[0][0]
            assert published_event.event_type == "intelligence.PacketBuilt"
            assert published_event.payload["symbol"] == "RELIANCE"
            assert published_event.correlation_id == cid
            assert published_event.causation_id == event.event_id

    def test_handles_malformed_snapshot_timestamp_gracefully(self) -> None:
        event = DomainEvent.create(
            event_type="technical_analysis.TechnicalAnalysisCompleted",
            payload={
                "symbol": "TCS",
                "snapshot_id": "snap-456",
                "exchange": "NSE",
                "snapshot_timestamp": "invalid-date",
            },
            correlation_id=uuid.uuid4(),
        )

        with patch("apps.intelligence.infrastructure.ta_completed_handler.get_event_bus") as mock_get_bus:
            mock_get_bus.return_value = MagicMock()

            handle_ta_completed(event)

    def test_prev_close_populated_from_tradingview(self) -> None:
        payload = {
            "symbol": "RELIANCE",
            "snapshot_id": "snap-789",
            "exchange": "NSE",
            "timeframe": "1D",
            "snapshot_timestamp": "2026-07-28T10:00:00+00:00",
            "indicators": {},
            "price": {
                "close": "2500.00",
                "prev_close": "2450.00",
                "change_pct": "2.04",
            },
        }
        occurred_at = datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc)
        packet = _build_packet(payload, occurred_at)
        assert packet.price_context.prev_close == Decimal("2450.00")
        assert packet.price_context.change_pct == Decimal("2.04")

    def test_prev_close_computed_from_previous_snapshot(self) -> None:
        payload = {
            "symbol": "RELIANCE",
            "snapshot_id": "snap-789",
            "exchange": "NSE",
            "timeframe": "1D",
            "snapshot_timestamp": "2026-07-28T10:00:00+00:00",
            "indicators": {},
            "price": {
                "close": "2600.00",
            },
        }
        occurred_at = datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc)
        with patch("apps.intelligence.infrastructure.ta_completed_handler.TASnapshotRepository") as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            from apps.technical_analysis.domain.entities import TASnapshot
            from apps.technical_analysis.domain.value_objects import PineMetadata
            prev_snapshot = TASnapshot(
                symbol="RELIANCE",
                exchange="NSE",
                timeframe="1D",
                indicators={},
                pine_metadata=PineMetadata(),
                raw_payload={"close": "2500.00"},
                snapshot_timestamp=datetime(2026, 7, 27, 10, 0, 0, tzinfo=timezone.utc),
            )
            mock_repo.find_by_symbol.return_value = [MagicMock(), prev_snapshot]
            packet = _build_packet(payload, occurred_at)
            assert packet.price_context.prev_close == Decimal("2500.00")
            expected_change = ((Decimal("2600.00") - Decimal("2500.00")) / Decimal("2500.00")) * Decimal("100")
            assert packet.price_context.change_pct == expected_change

    def test_missing_prev_close_preserves_none(self) -> None:
        payload = {
            "symbol": "RELIANCE",
            "snapshot_id": "snap-789",
            "exchange": "NSE",
            "timeframe": "1D",
            "snapshot_timestamp": "2026-07-28T10:00:00+00:00",
            "indicators": {},
            "price": {
                "close": "2600.00",
            },
        }
        occurred_at = datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc)
        with patch("apps.intelligence.infrastructure.ta_completed_handler.TASnapshotRepository") as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.find_by_symbol.return_value = []
            packet = _build_packet(payload, occurred_at)
            assert packet.price_context.prev_close is None
            assert packet.price_context.change_pct is None

    def test_get_prev_close_returns_none_on_lookup_failure(self) -> None:
        with patch("apps.intelligence.infrastructure.ta_completed_handler.TASnapshotRepository") as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.find_by_symbol.side_effect = Exception("DB error")
            result = _get_prev_close("RELIANCE", {})
            assert result is None

    def test_get_prev_close_uses_tradingview_value(self) -> None:
        result = _get_prev_close("RELIANCE", {"prev_close": "3124.50"})
        assert result == Decimal("3124.50")

    def test_optional_decimal_returns_none_for_none(self) -> None:
        assert _optional_decimal(None) is None

    def test_optional_decimal_returns_none_for_invalid(self) -> None:
        assert _optional_decimal("not-a-number") is None

    def test_optional_decimal_returns_decimal_for_valid(self) -> None:
        assert _optional_decimal("62.5") == Decimal("62.5")

    def test_detect_regime_value_detects_bullish(self) -> None:
        indicators = {
            "ema_50": "2550.00",
            "ema_200": "2500.00",
            "rsi_14": "60.0",
            "macd": "5.0",
            "macd_histogram": "2.0",
        }
        price = {"close": "2600.00", "volume": "1000", "avg_volume_20d": "500"}
        assert _detect_regime_value(indicators, price) == "BULLISH"

    def test_detect_regime_value_detects_bearish(self) -> None:
        indicators = {
            "ema_50": "2500.00",
            "ema_200": "2550.00",
            "rsi_14": "40.0",
            "macd": "-5.0",
            "macd_histogram": "-2.0",
        }
        price = {"close": "2450.00", "volume": "1000", "avg_volume_20d": "500"}
        assert _detect_regime_value(indicators, price) == "BEARISH"

    def test_detect_regime_value_ranging_without_trend_inputs(self) -> None:
        assert _detect_regime_value({}, {"close": "100.00"}) == "RANGING"

    def test_detect_regime_value_survives_partial_payload(self) -> None:
        assert _detect_regime_value({"rsi_14": "60"}, {"close": "2600.00"}) == "RANGING"

    def test_technical_context_optional_fields_preserve_none(self) -> None:
        payload = {
            "symbol": "RELIANCE",
            "snapshot_id": "snap-789",
            "exchange": "NSE",
            "timeframe": "1D",
            "snapshot_timestamp": "2026-07-28T10:00:00+00:00",
            "indicators": {},
            "price": {
                "close": "2500.00",
                "prev_close": "2450.00",
                "change_pct": "2.04",
            },
        }
        occurred_at = datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc)
        packet = _build_packet(payload, occurred_at)
        assert packet.technical_context.rsi_14 is None
        assert packet.technical_context.macd is None
        assert packet.technical_context.macd_signal is None
        assert packet.technical_context.bb_upper is None
        assert packet.technical_context.bb_lower is None
        assert packet.technical_context.ema_20 is None
        assert packet.technical_context.ema_50 is None
        assert packet.technical_context.ema_200 is None
        assert packet.technical_context.vwap is None

    def test_technical_context_indicator_values_are_preserved(self) -> None:
        payload = {
            "symbol": "RELIANCE",
            "snapshot_id": "snap-789",
            "exchange": "NSE",
            "timeframe": "1D",
            "snapshot_timestamp": "2026-07-28T10:00:00+00:00",
            "indicators": {
                "rsi_14": "62.5",
                "macd": "1.23",
                "bb_upper": "2550.00",
                "bb_lower": "2450.00",
                "ema_20": "2500.00",
                "ema_50": "2480.00",
                "ema_200": "2400.00",
                "vwap": "2490.00",
            },
            "price": {
                "close": "2500.00",
                "prev_close": "2450.00",
                "change_pct": "2.04",
            },
        }
        occurred_at = datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc)
        packet = _build_packet(payload, occurred_at)
        assert packet.technical_context.rsi_14 == Decimal("62.5")
        assert packet.technical_context.macd == Decimal("1.23")
        assert packet.technical_context.bb_upper == Decimal("2550.00")
        assert packet.technical_context.bb_lower == Decimal("2450.00")
        assert packet.technical_context.ema_20 == Decimal("2500.00")
        assert packet.technical_context.ema_50 == Decimal("2480.00")
        assert packet.technical_context.ema_200 == Decimal("2400.00")
        assert packet.technical_context.vwap == Decimal("2490.00")

    def test_build_packet_attaches_detected_regime(self) -> None:
        payload = {
            "symbol": "RELIANCE",
            "snapshot_id": "snap-789",
            "exchange": "NSE",
            "timeframe": "1D",
            "snapshot_timestamp": "2026-07-28T10:00:00+00:00",
            "indicators": {
                "ema_50": "2550.00",
                "ema_200": "2500.00",
                "rsi_14": "60.0",
            },
            "price": {"close": "2600.00", "volume": "1000", "avg_volume_20d": "500"},
        }
        occurred_at = datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc)
        packet = _build_packet(payload, occurred_at)
        assert packet.regime == "BULLISH"

    def test_missing_news_source_is_tagged_in_data_quality(self) -> None:
        payload = {
            "symbol": "RELIANCE",
            "snapshot_id": "snap-news-1",
            "exchange": "NSE",
            "timeframe": "1D",
            "snapshot_timestamp": "2026-07-28T10:00:00+00:00",
            "indicators": {},
            "price": {"close": "2500.00", "prev_close": "2450.00", "change_pct": "2.04"},
        }
        occurred_at = datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc)
        packet = _build_packet(payload, occurred_at)
        assert "news" in packet.data_quality.missing_sources

    def test_news_context_remains_unchecked_default(self) -> None:
        payload = {
            "symbol": "RELIANCE",
            "snapshot_id": "snap-news-2",
            "exchange": "NSE",
            "timeframe": "1D",
            "snapshot_timestamp": "2026-07-28T10:00:00+00:00",
            "indicators": {},
            "price": {"close": "2500.00", "prev_close": "2450.00", "change_pct": "2.04"},
        }
        occurred_at = datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc)
        packet = _build_packet(payload, occurred_at)
        assert packet.news_context == NewsContext()

    def test_news_context_populated_when_lookup_finds_headlines(self) -> None:
        from apps.intelligence.infrastructure import ta_completed_handler

        ta_completed_handler.get_news_context_service = lambda: _PopulatedNewsLookup()

        payload = {
            "symbol": "RELIANCE",
            "snapshot_id": "snap-news-4",
            "exchange": "NSE",
            "timeframe": "1D",
            "snapshot_timestamp": "2026-07-28T10:00:00+00:00",
            "indicators": {},
            "price": {"close": "2500.00", "prev_close": "2450.00", "change_pct": "2.04"},
        }
        occurred_at = datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc)
        packet = _build_packet(payload, occurred_at)
        assert "news" not in packet.data_quality.missing_sources
        assert len(packet.news_context.headlines) == 1
        assert packet.news_context.headlines[0].title == "RELIANCE Q2 profit beats estimates"
        assert packet.news_context.aggregate_sentiment == AggregateSentiment.POSITIVE
        assert packet.data_quality.quality_score == 1.0

    def test_quality_score_reflects_news_missing_penalty(self) -> None:
        payload = {
            "symbol": "RELIANCE",
            "snapshot_id": "snap-news-3",
            "exchange": "NSE",
            "timeframe": "1D",
            "snapshot_timestamp": "2026-07-28T10:00:00+00:00",
            "indicators": {},
            "price": {"close": "2500.00", "prev_close": "2450.00", "change_pct": "2.04"},
        }
        occurred_at = datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc)
        packet = _build_packet(payload, occurred_at)
        expected = 1.0 - (NEWS_MISSING_QUALITY_PENALTY * len(packet.data_quality.missing_sources))
        assert packet.data_quality.quality_score == expected
