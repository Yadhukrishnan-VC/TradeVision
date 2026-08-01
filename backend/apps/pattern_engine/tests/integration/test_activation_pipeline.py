from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from django.conf import settings
from django.test import override_settings

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import (
    get_event_bus,
    reset_event_bus,
)
from apps.intelligence.infrastructure.market_context_cache import MarketContextCache
from apps.intelligence.services import MarketContextService
from apps.pattern_engine.application.pattern_analysis_service import (
    PatternAnalysisService,
)
from apps.pattern_engine.domain.value_objects import FeatureVector
from apps.pattern_engine.infrastructure.event_handlers import (
    register_handlers as register_pattern_engine_handlers,
)
from apps.pattern_engine.infrastructure.event_publisher import (
    EVENT_TYPE as PATTERN_COMPLETED_EVENT_TYPE,
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


def _historical_vector() -> FeatureVector:
    return FeatureVector(
        symbol="RELIANCE",
        as_of=datetime(2024, 3, 1, 10, 0, tzinfo=TZ),
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


def _packet_built_payload() -> dict:
    return {
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


def _seed_vector() -> None:
    HistoricalFeatureVectorRepository().save_vector(
        _historical_vector(),
        outcome_price_change_pct=Decimal("2.10"),
        outcome_window_hours=24,
    )


@pytest.fixture(autouse=True)
def _fake_bus(redis_client) -> None:
    reset_event_bus()
    redis_client.flushdb()
    yield
    reset_event_bus()


class TestActivationBaseline:
    def test_pattern_engine_is_enabled_in_test_environment(self) -> None:
        assert settings.PATTERN_ENGINE_ENABLED is True
        assert settings.MARKET_CONTEXT_SCORING_ENABLED is True

    def test_pattern_engine_flag_is_env_driven_not_hard_coded(self) -> None:
        base_src = Path(settings.BASE_DIR) / "config" / "settings" / "base.py"
        src = base_src.read_text()
        assert '"PATTERN_ENGINE_ENABLED", default=False' in src
        assert '"PATTERN_ENGINE_ACCURACY_LOOKUP_ENABLED", default=False' in src
        assert '"MARKET_CONTEXT_SCORING_ENABLED", default=False' in src


class TestDoDSmokePipeline:
    """Proves PacketBuilt → PatternAnalysisCompleted → PatternContext →
    MarketContextService end to end with eager Celery and the fake bus."""

    @override_settings(EVENT_BUS_IMPLEMENTATION="fake")
    def test_packet_built_flows_to_market_context_cache(self, redis_client) -> None:
        _seed_vector()

        bus = get_event_bus()
        register_pattern_engine_handlers(bus)
        from apps.intelligence.infrastructure.event_handlers import (
            register_handlers as register_intelligence_handlers,
        )

        register_intelligence_handlers(bus)

        service = MarketContextService()
        with patch.object(service, "_get_pine_outputs") as mock_pine:
            mock_pine.return_value = {"1D": {}, "4h": {}, "1h": {}}
            context = service.build_signal_context(
                symbol="RELIANCE",
                packet=_packet(),
            )

        cache = MarketContextCache(redis_client=redis_client)
        cache.set("RELIANCE", context)
        assert cache.get("RELIANCE").pattern_alignment_note == "PATTERN_ENGINE_NOT_AVAILABLE"

        correlation_id = uuid.uuid4()
        event = DomainEvent.create(
            event_type="intelligence.PacketBuilt",
            payload=_packet_built_payload(),
            correlation_id=correlation_id,
        )
        bus.publish(event)

        run = PatternAnalysisRun.objects.get(symbol="RELIANCE")
        assert run.top_analogue_summary
        assert run.top_analogue_summary != ""

        cached = cache.get("RELIANCE")
        assert cached is not None
        assert cached.pattern_alignment_note == run.top_analogue_summary
        assert cached.pattern_alignment_note != "PATTERN_ENGINE_NOT_AVAILABLE"

        completed = [
            e
            for e in bus._published_events
            if e.event_type == PATTERN_COMPLETED_EVENT_TYPE
        ]
        assert len(completed) == 1
        assert completed[0].correlation_id == correlation_id

    @override_settings(EVENT_BUS_IMPLEMENTATION="fake")
    def test_duplicate_pattern_completed_delivery_is_idempotent(
        self, redis_client
    ) -> None:
        _seed_vector()
        bus = get_event_bus()
        register_pattern_engine_handlers(bus)
        from apps.intelligence.infrastructure.event_handlers import (
            register_handlers as register_intelligence_handlers,
        )

        register_intelligence_handlers(bus)

        cache = MarketContextCache(redis_client=redis_client)
        cache.set("RELIANCE", _base_signal_context())

        event = DomainEvent.create(
            event_type="intelligence.PacketBuilt",
            payload=_packet_built_payload(),
            correlation_id=uuid.uuid4(),
        )
        bus.publish(event)
        assert PatternAnalysisRun.objects.filter(symbol="RELIANCE").count() == 1

        completed = [
            e
            for e in bus._published_events
            if e.event_type == PATTERN_COMPLETED_EVENT_TYPE
        ]
        assert len(completed) == 1

        from apps.intelligence.infrastructure.pattern_context_handler import (
            handle_pattern_analysis_completed,
        )

        handle_pattern_analysis_completed(completed[0])
        first_note = cache.get("RELIANCE").pattern_alignment_note
        handle_pattern_analysis_completed(completed[0])

        cached = cache.get("RELIANCE")
        assert cached.pattern_alignment_note == first_note
        assert cached.pattern_alignment_note != "PATTERN_ENGINE_NOT_AVAILABLE"
        assert PatternAnalysisRun.objects.filter(symbol="RELIANCE").count() == 1


class TestFallbackPaths:
    def test_analyze_no_history_returns_insufficient_note(self) -> None:
        service = PatternAnalysisService(
            vector_repository=HistoricalFeatureVectorRepository(),
            run_repository=PatternAnalysisRunRepository(),
        )
        result = service.analyze(_packet(), correlation_id=uuid.uuid4())
        assert result.matched_patterns == ()
        assert "Insufficient historical data" in result.data_sufficiency_note
        assert "insufficient precomputed history" in result.top_analogue_summary

    @override_settings(EVENT_BUS_IMPLEMENTATION="fake")
    def test_no_history_packet_built_never_breaks_pipeline(self, redis_client) -> None:
        bus = get_event_bus()
        register_pattern_engine_handlers(bus)
        from apps.intelligence.infrastructure.event_handlers import (
            register_handlers as register_intelligence_handlers,
        )

        register_intelligence_handlers(bus)

        cache = MarketContextCache(redis_client=redis_client)
        cache.set("RELIANCE", _base_signal_context())

        event = DomainEvent.create(
            event_type="intelligence.PacketBuilt",
            payload=_packet_built_payload(),
            correlation_id=uuid.uuid4(),
        )
        bus.publish(event)

        cached = cache.get("RELIANCE")
        assert cached is not None
        assert "insufficient precomputed history" in cached.pattern_alignment_note
        assert cached.pattern_alignment_note != "PATTERN_ENGINE_NOT_AVAILABLE"

    @override_settings(EVENT_BUS_IMPLEMENTATION="fake")
    def test_pattern_context_attach_noop_when_no_cache_entry(self, redis_client) -> None:
        cache = MarketContextCache(redis_client=redis_client)
        from apps.intelligence.infrastructure.pattern_context_handler import (
            handle_pattern_analysis_completed,
        )

        event = DomainEvent.create(
            event_type=PATTERN_COMPLETED_EVENT_TYPE,
            payload={
                "symbol": "RELIANCE",
                "similar_dates": [],
                "top_analogue_summary": "Similar to 2024-03-01",
            },
            correlation_id=uuid.uuid4(),
        )
        handle_pattern_analysis_completed(event)
        assert cache.get("RELIANCE") is None


class TestAccuracyLookup:
    def test_accuracy_lookup_disabled_yields_none(self) -> None:
        _seed_vector()
        service = PatternAnalysisService(
            vector_repository=HistoricalFeatureVectorRepository(),
            run_repository=PatternAnalysisRunRepository(),
        )
        with override_settings(PATTERN_ENGINE_ACCURACY_LOOKUP_ENABLED=False):
            result = service.analyze(_packet(), correlation_id=uuid.uuid4())
        assert result.historical_recommendation_accuracy is None

    @override_settings(PATTERN_ENGINE_ACCURACY_LOOKUP_ENABLED=True)
    def test_accuracy_lookup_failure_degrades_to_none(self) -> None:
        _seed_vector()
        service = PatternAnalysisService(
            vector_repository=HistoricalFeatureVectorRepository(),
            run_repository=PatternAnalysisRunRepository(),
        )
        with patch(
            "apps.pattern_engine.infrastructure.accuracy_lookup.get_historical_recommendation_accuracy",
            side_effect=RuntimeError("Trader Memory down"),
        ):
            result = service.analyze(_packet(), correlation_id=uuid.uuid4())

        assert result.historical_recommendation_accuracy is None
        assert result.matched_patterns


def _base_signal_context():
    from datetime import datetime, timezone

    from apps.intelligence.domain.market_regime import (
        MarketRegime,
        MultiTimeframeAlignment,
    )
    from apps.intelligence.services import SignalContext

    return SignalContext(
        symbol="RELIANCE",
        timestamp=datetime.now(timezone.utc),
        market_regime=MarketRegime.RANGING,
        multi_timeframe_alignment=MultiTimeframeAlignment.NEUTRAL,
    )
