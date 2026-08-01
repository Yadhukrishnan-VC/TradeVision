from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.pattern_engine.application.pattern_analysis_service import (
    PatternAnalysisService,
)
from apps.pattern_engine.domain.exceptions import PatternEngineError
from apps.pattern_engine.infrastructure.repositories import (
    decode_feature_vector,
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

TZ = timezone.utc


class _FakeVectorRow:
    """Mimics a HistoricalFeatureVector ORM row (attribute access)."""

    def __init__(
        self,
        *,
        features: dict,
        subsequent_price_change_pct,
        subsequent_window_hours: int,
    ) -> None:
        self.features = features
        self.subsequent_price_change_pct = subsequent_price_change_pct
        self.subsequent_window_hours = subsequent_window_hours


class FakeVectorRepo:
    """Minimal in-memory stand-in for HistoricalFeatureVectorRepository."""

    def __init__(self, rows: list | None = None) -> None:
        self.rows = rows or []
        self.saved = []

    def find_recent(self, symbol: str, before, limit: int = 500):
        return [r for r in self.rows if r.features["symbol"] == symbol.upper()]

    def to_domain(self, row):
        return decode_feature_vector(row.features, symbol=row.features["symbol"])


class FakeRunRepo:
    def __init__(self) -> None:
        self.saved = []

    def save_result(self, result) -> None:
        self.saved.append(result)


def _row(
    *,
    symbol: str,
    as_of,
    price_change_pct: str,
    rsi_14: str | None = "60.0",
    trend: str = "UPTREND",
    outcome: str | None = "1.5",
    macd_histogram: str | None = "0.5",
    nifty_change_pct: str = "0.3",
    bb_position: str | None = "0.6",
) -> dict:
    features = {
        "symbol": symbol,
        "as_of": as_of.isoformat(),
        "price_change_pct": price_change_pct,
        "gap_pct": "0.2",
        "volume_ratio": "1.1",
        "rsi_14": rsi_14,
        "macd_histogram": macd_histogram,
        "bb_position": bb_position,
        "trend": trend,
        "pcr": None,
        "oi_change_direction": None,
        "nifty_change_pct": nifty_change_pct,
        "crude_oil_pct": None,
        "fii_flow_direction": None,
        "sector_trend_direction": None,
        "advance_decline_ratio": None,
    }
    return _FakeVectorRow(
        features=features,
        subsequent_price_change_pct=Decimal(outcome) if outcome is not None else None,
        subsequent_window_hours=24,
    )


def _packet(change_pct: str = "1.5") -> IntelligencePacket:
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
            change_pct=Decimal(change_pct),
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


class TestPatternAnalysisService:
    def test_rejects_stale_packet(self) -> None:
        packet = _packet()
        packet = IntelligencePacket(
            symbol=packet.symbol,
            timestamp=packet.timestamp,
            freshness_validated=False,
            price_context=packet.price_context,
            technical_context=packet.technical_context,
            breadth_context=packet.breadth_context,
            news_context=packet.news_context,
            data_quality=packet.data_quality,
        )
        service = PatternAnalysisService(FakeVectorRepo(), FakeRunRepo())
        with pytest.raises(PatternEngineError):
            service.analyze(packet, correlation_id=uuid.uuid4())

    def test_empty_history_returns_empty_result(self) -> None:
        service = PatternAnalysisService(FakeVectorRepo([]), FakeRunRepo())
        result = service.analyze(_packet(), correlation_id=uuid.uuid4())
        assert result.matched_patterns == ()
        assert result.confidence_contribution == Decimal(0)
        assert result.data_sufficiency_note

    def test_finds_top_analogue(self) -> None:
        repo = FakeVectorRepo(
            [
                _row(
                    symbol="RELIANCE",
                    as_of=datetime(2024, 3, 1, 10, 0, tzinfo=TZ),
                    price_change_pct="1.6",
                    outcome="2.1",
                ),
                _row(
                    symbol="RELIANCE",
                    as_of=datetime(2024, 2, 1, 10, 0, tzinfo=TZ),
                    price_change_pct="-6.0",
                    rsi_14="15.0",
                    trend="DOWNTREND",
                    macd_histogram="-2.0",
                    nifty_change_pct="-1.8",
                    bb_position="0.1",
                    outcome="-4.0",
                ),
            ]
        )
        run_repo = FakeRunRepo()
        service = PatternAnalysisService(repo, run_repo)
        result = service.analyze(_packet(), correlation_id=uuid.uuid4())

        assert len(result.matched_patterns) == 1  # far analogue below threshold
        top = result.matched_patterns[0]
        assert top.date_str == "2024-03-01"
        assert top.similarity.overall > Decimal("0.7")
        assert top.outcome_summary.startswith("On 2024-03-01")
        assert "2.10%" in top.outcome_summary
        assert result.top_analogue_summary
        assert result.confidence_contribution > Decimal(0)
        assert len(result.evidence) >= 2
        assert run_repo.saved and run_repo.saved[0].id == result.id

    def test_persists_empty_history_run(self) -> None:
        run_repo = FakeRunRepo()
        service = PatternAnalysisService(FakeVectorRepo([]), run_repo)
        result = service.analyze(_packet(), correlation_id=uuid.uuid4())
        assert run_repo.saved and run_repo.saved[0].id == result.id

    def test_confidence_contribution_is_bounded(self) -> None:
        repo = FakeVectorRepo(
            [
                _row(
                    symbol="RELIANCE",
                    as_of=datetime(2024, 3, 1, 10, 0, tzinfo=TZ),
                    price_change_pct="1.6",
                ),
            ]
        )
        service = PatternAnalysisService(repo, FakeRunRepo())
        result = service.analyze(_packet(), correlation_id=uuid.uuid4())
        assert Decimal(0) <= result.confidence_contribution <= Decimal("0.5")

    def test_outcome_none_produces_graceful_summary(self) -> None:
        repo = FakeVectorRepo(
            [
                _row(
                    symbol="RELIANCE",
                    as_of=datetime(2024, 3, 1, 10, 0, tzinfo=TZ),
                    price_change_pct="1.6",
                    outcome=None,
                ),
            ]
        )
        service = PatternAnalysisService(repo, FakeRunRepo())
        result = service.analyze(_packet(), correlation_id=uuid.uuid4())
        assert result.matched_patterns
        assert "no subsequent outcome" in result.matched_patterns[0].outcome_summary

    def test_accuracy_flag_off_yields_none(self) -> None:
        repo = FakeVectorRepo(
            [
                _row(
                    symbol="RELIANCE",
                    as_of=datetime(2024, 3, 1, 10, 0, tzinfo=TZ),
                    price_change_pct="1.6",
                ),
            ]
        )
        with override_settings(PATTERN_ENGINE_ACCURACY_LOOKUP_ENABLED=False):
            service = PatternAnalysisService(repo, FakeRunRepo())
            result = service.analyze(_packet(), correlation_id=uuid.uuid4())
        assert result.historical_recommendation_accuracy is None

    def test_accuracy_flag_on_with_lookup_failure_degrades_to_none(self) -> None:
        repo = FakeVectorRepo(
            [
                _row(
                    symbol="RELIANCE",
                    as_of=datetime(2024, 3, 1, 10, 0, tzinfo=TZ),
                    price_change_pct="1.6",
                ),
            ]
        )
        with (
            override_settings(PATTERN_ENGINE_ACCURACY_LOOKUP_ENABLED=True),
            patch(
                "apps.pattern_engine.infrastructure.accuracy_lookup."
                "get_historical_recommendation_accuracy",
                side_effect=Exception("trader memory down"),
            ),
        ):
            service = PatternAnalysisService(repo, FakeRunRepo())
            result = service.analyze(_packet(), correlation_id=uuid.uuid4())
        assert result.historical_recommendation_accuracy is None

    def test_accuracy_flag_on_populates_accuracy(self) -> None:
        repo = FakeVectorRepo(
            [
                _row(
                    symbol="RELIANCE",
                    as_of=datetime(2024, 3, 1, 10, 0, tzinfo=TZ),
                    price_change_pct="1.6",
                ),
            ]
        )
        with (
            override_settings(PATTERN_ENGINE_ACCURACY_LOOKUP_ENABLED=True),
            patch(
                "apps.pattern_engine.infrastructure.accuracy_lookup."
                "get_historical_recommendation_accuracy",
                return_value=Decimal("0.65"),
            ),
        ):
            service = PatternAnalysisService(repo, FakeRunRepo())
            result = service.analyze(_packet(), correlation_id=uuid.uuid4())
        assert result.historical_recommendation_accuracy == Decimal("0.65")
