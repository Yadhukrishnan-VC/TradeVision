from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any

from apps.pattern_engine.domain.entities import (
    EvidenceItem,
    MatchedPattern,
    PatternAnalysisResult,
)
from apps.pattern_engine.domain.value_objects import (
    FeatureVector,
    SimilarityScore,
)
from apps.pattern_engine.infrastructure.models import (
    HistoricalFeatureVector,
    PatternAnalysisRun,
)
from core.repository import BaseRepository

logger = logging.getLogger(__name__)


def _s(value: Any) -> str:
    """Stringify a Decimal/float without losing precision (used for JSON)."""
    return str(value)


def _decode_decimal(value: Any) -> Any:
    from decimal import Decimal, InvalidOperation

    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return value


class HistoricalFeatureVectorRepository(BaseRepository[HistoricalFeatureVector]):
    """Persistence for precomputed historical feature vectors.

    Domain objects are stored as JSON on the ORM row (Decimals as strings) and
    reconstructed on read so the service layer can stay free of ORM knowledge.
    """

    def get_by_id(self, entity_id: uuid.UUID) -> HistoricalFeatureVector | None:
        try:
            return HistoricalFeatureVector.objects.get(id=entity_id)
        except HistoricalFeatureVector.DoesNotExist:
            return None

    def list(self, **filters: Any) -> list[HistoricalFeatureVector]:
        return list(HistoricalFeatureVector.objects.filter(**filters))

    def create(self, entity: HistoricalFeatureVector) -> HistoricalFeatureVector:
        entity.full_clean()
        entity.save()
        return entity

    def update(self, entity: HistoricalFeatureVector) -> HistoricalFeatureVector:
        entity.full_clean()
        entity.save()
        return entity

    def delete(self, entity_id: uuid.UUID) -> None:
        HistoricalFeatureVector.objects.filter(id=entity_id).delete()

    def exists(self, entity_id: uuid.UUID) -> bool:
        return HistoricalFeatureVector.objects.filter(id=entity_id).exists()

    def count(self, **filters: Any) -> int:
        return HistoricalFeatureVector.objects.filter(**filters).count()

    def save_vector(
        self,
        vector: FeatureVector,
        outcome_price_change_pct: Any = None,
        outcome_window_hours: int = 24,
        data_sufficiency_note: str = "",
    ) -> HistoricalFeatureVector:
        """Upsert a precomputed historical vector keyed by ``(symbol, as_of)``."""
        defaults = {
            "features": encode_feature_vector(vector),
            "subsequent_price_change_pct": (
                None
                if outcome_price_change_pct is None
                else _decode_decimal(outcome_price_change_pct)
            ),
            "subsequent_window_hours": outcome_window_hours,
            "data_sufficiency_note": data_sufficiency_note,
        }
        obj, _ = HistoricalFeatureVector.objects.update_or_create(
            symbol=vector.symbol.upper(),
            as_of=vector.as_of.date()
            if isinstance(vector.as_of, datetime)
            else vector.as_of,
            defaults=defaults,
        )
        return obj

    def find_recent(
        self,
        symbol: str,
        before: date | datetime,
        limit: int = 500,
    ) -> list[HistoricalFeatureVector]:
        """Return historical vectors for ``symbol`` strictly before ``before``."""
        qs = HistoricalFeatureVector.objects.filter(
            symbol=symbol.upper(),
            as_of__lt=before,
        )
        return list(qs.order_by("-as_of")[:limit])

    def find_for_symbol(
        self, symbol: str, limit: int = 500
    ) -> list[HistoricalFeatureVector]:
        return list(
            HistoricalFeatureVector.objects.filter(symbol=symbol.upper()).order_by(
                "-as_of"
            )[:limit]
        )

    @staticmethod
    def to_domain(obj: HistoricalFeatureVector) -> FeatureVector:
        return decode_feature_vector(obj.features, symbol=obj.symbol)


class PatternAnalysisRunRepository(BaseRepository[PatternAnalysisRun]):
    """Persistence for pattern analysis runs (rich results)."""

    def get_by_id(self, entity_id: uuid.UUID) -> PatternAnalysisRun | None:
        try:
            return PatternAnalysisRun.objects.get(id=entity_id)
        except PatternAnalysisRun.DoesNotExist:
            return None

    def list(self, **filters: Any) -> list[PatternAnalysisRun]:
        return list(PatternAnalysisRun.objects.filter(**filters))

    def create(self, entity: PatternAnalysisRun) -> PatternAnalysisRun:
        entity.full_clean()
        entity.save()
        return entity

    def update(self, entity: PatternAnalysisRun) -> PatternAnalysisRun:
        entity.full_clean()
        entity.save()
        return entity

    def delete(self, entity_id: uuid.UUID) -> None:
        PatternAnalysisRun.objects.filter(id=entity_id).delete()

    def exists(self, entity_id: uuid.UUID) -> bool:
        return PatternAnalysisRun.objects.filter(id=entity_id).exists()

    def count(self, **filters: Any) -> int:
        return PatternAnalysisRun.objects.filter(**filters).count()

    def save_result(self, result: PatternAnalysisResult) -> PatternAnalysisRun:
        obj = PatternAnalysisRun(
            id=result.id,
            symbol=result.symbol.upper(),
            as_of=result.as_of,
            top_analogue_summary=result.top_analogue_summary,
            confidence_contribution=result.confidence_contribution,
            historical_recommendation_accuracy=result.historical_recommendation_accuracy,
            matched_patterns=[
                encode_matched_pattern(pattern) for pattern in result.matched_patterns
            ],
            evidence=[encode_evidence_item(item) for item in result.evidence],
            data_sufficiency_note=result.data_sufficiency_note,
        )
        obj.full_clean()
        obj.save()
        return obj

    @staticmethod
    def to_domain(obj: PatternAnalysisRun) -> PatternAnalysisResult:
        return decode_analysis_run(obj)


# ---------------------------------------------------------------------------
# Encode/decode helpers — Decimal values stored as strings for precision
# ---------------------------------------------------------------------------


def encode_feature_vector(vector: FeatureVector) -> dict[str, Any]:
    return {
        "symbol": vector.symbol,
        "as_of": vector.as_of.isoformat(),
        "price_change_pct": _s(vector.price_change_pct),
        "gap_pct": _s(vector.gap_pct),
        "volume_ratio": _s(vector.volume_ratio),
        "rsi_14": _s(vector.rsi_14) if vector.rsi_14 is not None else None,
        "macd_histogram": _s(vector.macd_histogram)
        if vector.macd_histogram is not None
        else None,
        "bb_position": _s(vector.bb_position)
        if vector.bb_position is not None
        else None,
        "trend": vector.trend.value if vector.trend is not None else None,
        "pcr": _s(vector.pcr) if vector.pcr is not None else None,
        "oi_change_direction": vector.oi_change_direction,
        "nifty_change_pct": _s(vector.nifty_change_pct),
        "crude_oil_pct": _s(vector.crude_oil_pct)
        if vector.crude_oil_pct is not None
        else None,
        "fii_flow_direction": vector.fii_flow_direction,
        "sector_trend_direction": vector.sector_trend_direction,
        "advance_decline_ratio": _s(vector.advance_decline_ratio)
        if vector.advance_decline_ratio is not None
        else None,
    }


def decode_feature_vector(
    data: dict[str, Any],
    *,
    symbol: str | None = None,
) -> FeatureVector:
    from core.events.event_types import MarketTrend

    as_of = datetime.fromisoformat(data["as_of"])
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)

    trend_raw = data.get("trend")
    trend = None
    if trend_raw is not None:
        try:
            trend = MarketTrend(str(trend_raw).upper())
        except ValueError:
            trend = None

    return FeatureVector(
        symbol=(symbol or data.get("symbol", "")).upper(),
        as_of=as_of,
        price_change_pct=_decode_decimal(data["price_change_pct"]),
        gap_pct=_decode_decimal(data["gap_pct"]),
        volume_ratio=_decode_decimal(data["volume_ratio"]),
        rsi_14=_decode_decimal(data.get("rsi_14")),
        macd_histogram=_decode_decimal(data.get("macd_histogram")),
        bb_position=_decode_decimal(data.get("bb_position")),
        trend=trend,
        pcr=_decode_decimal(data.get("pcr")),
        oi_change_direction=data.get("oi_change_direction"),
        nifty_change_pct=_decode_decimal(data.get("nifty_change_pct", "0")),
        crude_oil_pct=_decode_decimal(data.get("crude_oil_pct")),
        fii_flow_direction=data.get("fii_flow_direction"),
        sector_trend_direction=data.get("sector_trend_direction"),
        advance_decline_ratio=_decode_decimal(data.get("advance_decline_ratio")),
    )


def encode_matched_pattern(pattern: MatchedPattern) -> dict[str, Any]:
    return {
        "date_str": pattern.date_str,
        "similarity_overall": _s(pattern.similarity.overall),
        "similarity_feature_distance": _s(pattern.similarity.feature_distance),
        "per_group_distance": {
            k: _s(v) for k, v in pattern.similarity.per_group_distance.items()
        },
        "outcome_summary": pattern.outcome_summary,
        "subsequent_price_change_pct": _s(pattern.subsequent_price_change_pct),
        "subsequent_window_hours": pattern.subsequent_window_hours,
    }


def decode_matched_pattern(data: dict[str, Any]) -> MatchedPattern:
    similarity = SimilarityScore(
        overall=_decode_decimal(data["similarity_overall"]),
        feature_distance=_decode_decimal(data["similarity_feature_distance"]),
        per_group_distance={
            k: _decode_decimal(v) for k, v in data.get("per_group_distance", {}).items()
        },
    )
    return MatchedPattern(
        date_str=data["date_str"],
        similarity=similarity,
        outcome_summary=data["outcome_summary"],
        subsequent_price_change_pct=_decode_decimal(
            data["subsequent_price_change_pct"]
        ),
        subsequent_window_hours=int(data.get("subsequent_window_hours", 24)),
    )


def encode_evidence_item(item: EvidenceItem) -> dict[str, str]:
    return {
        "description": item.description,
        "supporting_metric": item.supporting_metric,
        "value": item.value,
    }


def decode_analysis_run(obj: PatternAnalysisRun) -> PatternAnalysisResult:
    matched_patterns = tuple(
        decode_matched_pattern(item) for item in (obj.matched_patterns or [])
    )
    evidence = tuple(
        EvidenceItem(
            description=item.get("description", ""),
            supporting_metric=item.get("supporting_metric", ""),
            value=item.get("value", ""),
        )
        for item in (obj.evidence or [])
    )
    return PatternAnalysisResult(
        id=obj.id,
        symbol=obj.symbol,
        as_of=obj.as_of,
        matched_patterns=matched_patterns,
        top_analogue_summary=obj.top_analogue_summary,
        historical_recommendation_accuracy=obj.historical_recommendation_accuracy,
        confidence_contribution=obj.confidence_contribution,
        evidence=evidence,
        data_sufficiency_note=obj.data_sufficiency_note,
    )


__all__ = [
    "HistoricalFeatureVectorRepository",
    "PatternAnalysisRunRepository",
    "decode_analysis_run",
    "decode_feature_vector",
    "decode_matched_pattern",
    "encode_evidence_item",
    "encode_feature_vector",
    "encode_matched_pattern",
]
