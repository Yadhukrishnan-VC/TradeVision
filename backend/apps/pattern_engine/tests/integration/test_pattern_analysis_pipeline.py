from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.pattern_engine.application.pattern_analysis_service import (
    PatternAnalysisService,
)
from apps.pattern_engine.domain.value_objects import FeatureVector
from apps.pattern_engine.infrastructure.event_publisher import (
    EVENT_TYPE,
    publish_pattern_analysis_completed,
)
from apps.pattern_engine.infrastructure.models import PatternAnalysisRun
from apps.pattern_engine.infrastructure.repositories import (
    HistoricalFeatureVectorRepository,
    PatternAnalysisRunRepository,
)
from core.events.event_types import (
    BreadthContext,
    CircuitStatus,
    DataQuality,
    IntelligencePacket,
    MarketTrend,
    NewsContext,
    PriceContext,
    TechnicalContext,
)

pytestmark = pytest.mark.django_db

TZ = timezone.utc


def _historical_vector(
    symbol: str = "RELIANCE", as_of: datetime | None = None
) -> FeatureVector:
    return FeatureVector(
        symbol=symbol,
        as_of=as_of or datetime(2024, 3, 1, 10, 0, tzinfo=TZ),
        price_change_pct=Decimal("1.60"),
        gap_pct=Decimal("0.20"),
        volume_ratio=Decimal("1.10"),
        rsi_14=Decimal("60.0"),
        macd_histogram=Decimal("0.50"),
        bb_position=Decimal("0.60"),
        trend=MarketTrend.UPTREND,
        pcr=None,
        oi_change_direction=None,
        nifty_change_pct=Decimal("0.30"),
        crude_oil_pct=None,
        fii_flow_direction=None,
        sector_trend_direction=None,
        advance_decline_ratio=None,
    )


def _packet() -> IntelligencePacket:
    return IntelligencePacket(
        symbol="RELIANCE",
        timestamp=datetime(2024, 3, 18, 10, 0, tzinfo=TZ),
        freshness_validated=True,
        price_context=PriceContext(
            current_price=Decimal(100),
            open_price=Decimal(99),
            high=Decimal(101),
            low=Decimal("98.5"),
            volume=1_200_000,
            avg_volume_20d=1_000_000,
            circuit_status=CircuitStatus.NORMAL,
            prev_close=Decimal("98.5"),
            change_pct=Decimal("1.5"),
        ),
        technical_context=TechnicalContext(
            trend=MarketTrend.UPTREND,
            rsi_14=Decimal("62.0"),
            macd_histogram=Decimal("0.8"),
            bb_upper=Decimal(105),
            bb_lower=Decimal(95),
        ),
        breadth_context=BreadthContext(
            sector_index_change_pct=Decimal("0.4"),
            sector_advance_decline=Decimal("1.4"),
            nifty_change_pct=Decimal("0.3"),
            sensex_change_pct=Decimal("0.2"),
        ),
        news_context=NewsContext(),
        data_quality=DataQuality(),
    )


class TestPatternAnalysisPipeline:
    def test_end_to_end_with_real_db_and_intelligence_handler(self) -> None:
        vector_repo = HistoricalFeatureVectorRepository()
        vector_repo.save_vector(
            _historical_vector(),
            outcome_price_change_pct=Decimal("2.10"),
            outcome_window_hours=24,
        )

        service = PatternAnalysisService(
            vector_repository=vector_repo,
            run_repository=PatternAnalysisRunRepository(),
        )
        correlation_id = uuid.uuid4()
        result = service.analyze(_packet(), correlation_id=correlation_id)

        assert result.matched_patterns
        top = result.matched_patterns[0]
        assert top.date_str == "2024-03-01"
        assert top.similarity.overall > Decimal("0.9")

        persisted = PatternAnalysisRun.objects.get(id=result.id)
        assert persisted.symbol == "RELIANCE"
        assert persisted.top_analogue_summary == result.top_analogue_summary

        event = publish_pattern_analysis_completed(
            result,
            correlation_id=correlation_id,
            causation_id=uuid.uuid4(),
        )
        assert event.event_type == EVENT_TYPE

        with patch(
            "apps.intelligence.infrastructure.pattern_context_handler.MarketContextCache"
        ) as mock_cache_cls:
            mock_cache = MagicMock()
            mock_cache_cls.return_value = mock_cache
            from apps.intelligence.infrastructure.pattern_context_handler import (
                handle_pattern_analysis_completed,
            )

            handle_pattern_analysis_completed(event)

        mock_cache_cls.return_value.attach_pattern_context.assert_called_once()
        call_args = mock_cache_cls.return_value.attach_pattern_context.call_args
        assert call_args[0][0] == "RELIANCE"
        pattern_ctx = call_args[0][1]
        assert pattern_ctx.top_analogue_summary == result.top_analogue_summary
        assert pattern_ctx.similar_dates
        assert str(pattern_ctx.similar_dates[0].similarity_score) == str(
            result.matched_patterns[0].similarity.overall
        )

    def test_event_payload_matches_intelligence_fixture_contract(self) -> None:
        """The published payload must deserialise with the unmodified
        ``apps.intelligence`` contract (symbol, similar_dates[*].{
        date_str, similarity_score, outcome_summary}, top_analogue_summary)."""
        vector_repo = HistoricalFeatureVectorRepository()
        vector_repo.save_vector(
            _historical_vector(),
            outcome_price_change_pct=Decimal("2.10"),
            outcome_window_hours=24,
        )

        service = PatternAnalysisService(
            vector_repository=vector_repo,
            run_repository=PatternAnalysisRunRepository(),
        )
        result = service.analyze(_packet(), correlation_id=uuid.uuid4())

        event = publish_pattern_analysis_completed(result, correlation_id=uuid.uuid4())
        payload = event.payload
        assert payload["symbol"] == "RELIANCE"
        assert isinstance(payload["similar_dates"], list)
        for item in payload["similar_dates"]:
            assert set(item) == {"date_str", "similarity_score", "outcome_summary"}
        assert isinstance(payload["top_analogue_summary"], str)

        from apps.intelligence.infrastructure.pattern_context_handler import (
            _deserialize_pattern_context,
        )

        pattern_ctx = _deserialize_pattern_context(payload)
        assert pattern_ctx is not None
        assert pattern_ctx.top_analogue_summary == result.top_analogue_summary
        assert len(pattern_ctx.similar_dates) == len(result.matched_patterns)

    def test_no_history_path_returns_empty_result(self) -> None:
        service = PatternAnalysisService(
            vector_repository=HistoricalFeatureVectorRepository(),
            run_repository=PatternAnalysisRunRepository(),
        )
        result = service.analyze(_packet(), correlation_id=uuid.uuid4())
        assert result.matched_patterns == ()
        assert result.confidence_contribution == Decimal(0)
        assert "Insufficient historical data" in result.data_sufficiency_note

        persisted = PatternAnalysisRun.objects.get(id=result.id)
        assert persisted.symbol == "RELIANCE"

    def test_trigger_event_dispatches_analysis(self) -> None:
        """Subscribing to ``intelligence.PacketBuilt`` dispatches a celery run."""
        from django.test import override_settings

        from apps.pattern_engine.infrastructure.event_handlers import (
            handle_packet_built,
        )

        payload = {
            "symbol": "RELIANCE",
            "snapshot_timestamp": "2024-03-18T10:00:00+00:00",
            "packet_data": {
                "symbol": "RELIANCE",
                "timestamp": "2024-03-18T10:00:00+00:00",
                "freshness_validated": True,
                "price_context": {
                    "current_price": "100",
                    "open_price": "99",
                    "high": "101",
                    "low": "98.5",
                    "volume": "1200000",
                    "avg_volume_20d": "1000000",
                    "circuit_status": "NORMAL",
                    "prev_close": "98.5",
                    "change_pct": "1.5",
                },
                "technical_context": {
                    "trend": "UPTREND",
                    "rsi_14": "62.0",
                    "macd_histogram": "0.8",
                    "bb_upper": "105",
                    "bb_lower": "95",
                },
                "breadth_context": {
                    "sector_index_change_pct": "0.4",
                    "sector_advance_decline": "1.4",
                    "nifty_change_pct": "0.3",
                    "sensex_change_pct": "0.2",
                },
            },
        }
        event = DomainEvent.create(
            event_type="intelligence.PacketBuilt",
            payload=payload,
            correlation_id=uuid.uuid4(),
        )

        with (
            override_settings(PATTERN_ENGINE_ENABLED=True),
            patch(
                "apps.pattern_engine.infrastructure.event_handlers.run_pattern_analysis"
            ) as mock_task,
        ):
            handle_packet_built(event)
            mock_task.delay.assert_called_once()
            call_kwargs = mock_task.delay.call_args[1]
            assert call_kwargs["symbol"] == "RELIANCE"
            assert call_kwargs["packet_data"]["symbol"] == "RELIANCE"
            assert call_kwargs["correlation_id"] == str(event.correlation_id)
            assert call_kwargs["causation_id"] == str(event.event_id)

    def test_handler_skips_when_disabled(self) -> None:
        from django.test import override_settings

        from apps.pattern_engine.infrastructure.event_handlers import (
            handle_packet_built,
        )

        event = DomainEvent.create(
            event_type="intelligence.PacketBuilt",
            payload={"symbol": "RELIANCE", "packet_data": {}},
            correlation_id=uuid.uuid4(),
        )
        with (
            override_settings(PATTERN_ENGINE_ENABLED=False),
            patch(
                "apps.pattern_engine.infrastructure.event_handlers.run_pattern_analysis"
            ) as mock_task,
        ):
            handle_packet_built(event)
            mock_task.delay.assert_not_called()
