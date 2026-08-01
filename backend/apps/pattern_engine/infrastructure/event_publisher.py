from __future__ import annotations

import logging
import uuid
from typing import Any

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.pattern_engine.domain.entities import (
    MatchedPattern,
    PatternAnalysisResult,
)

logger = logging.getLogger(__name__)

EVENT_TYPE = "pattern_engine.PatternAnalysisCompleted"


def build_payload(result: PatternAnalysisResult) -> dict[str, Any]:
    """Map a rich ``PatternAnalysisResult`` to the event payload.

    Frozen contract (consumed by ``apps.intelligence`` unmodified)::

        symbol:            str
        similar_dates:     [{"date_str", "similarity_score", "outcome_summary"}]
        top_analogue_summary: str

    Additive keys (ignored by today's consumers, kept for future phases):
    ``run_id``, ``feature_distance``, ``per_group_distance``,
    ``matching_patterns`` (rich per-pattern detail),
    ``historical_recommendation_accuracy``, ``confidence_contribution``,
    ``evidence``, ``data_sufficiency_note``.
    """
    similar_dates = [
        {
            "date_str": pattern.date_str,
            "similarity_score": str(pattern.similarity.overall),
            "outcome_summary": pattern.outcome_summary,
        }
        for pattern in result.matched_patterns
    ]

    matching_patterns = [
        _pattern_detail(pattern) for pattern in result.matched_patterns
    ]

    payload: dict[str, Any] = {
        "symbol": result.symbol.upper(),
        "similar_dates": similar_dates,
        "top_analogue_summary": result.top_analogue_summary,
        # --- additive extensions (optional for consumers) ---
        "run_id": str(result.id),
        "feature_distance": (
            str(result.matched_patterns[0].similarity.feature_distance)
            if result.matched_patterns
            else None
        ),
        "per_group_distance": (
            {
                k: str(v)
                for k, v in result.matched_patterns[
                    0
                ].similarity.per_group_distance.items()
            }
            if result.matched_patterns
            else {}
        ),
        "matching_patterns": matching_patterns,
        "historical_recommendation_accuracy": (
            str(result.historical_recommendation_accuracy)
            if result.historical_recommendation_accuracy is not None
            else None
        ),
        "confidence_contribution": str(result.confidence_contribution),
        "evidence": [
            {
                "description": item.description,
                "supporting_metric": item.supporting_metric,
                "value": item.value,
            }
            for item in result.evidence
        ],
        "data_sufficiency_note": result.data_sufficiency_note,
    }
    return payload


def _pattern_detail(pattern: MatchedPattern) -> dict[str, Any]:
    return {
        "date_str": pattern.date_str,
        "similarity_score": str(pattern.similarity.overall),
        "outcome_summary": pattern.outcome_summary,
        "feature_distance": str(pattern.similarity.feature_distance),
        "per_group_distance": {
            k: str(v) for k, v in pattern.similarity.per_group_distance.items()
        },
        "subsequent_price_change_pct": str(pattern.subsequent_price_change_pct),
        "subsequent_window_hours": pattern.subsequent_window_hours,
    }


def publish_pattern_analysis_completed(
    result: PatternAnalysisResult,
    *,
    correlation_id: uuid.UUID,
    causation_id: uuid.UUID | None = None,
) -> DomainEvent:
    """Publish ``pattern_engine.PatternAnalysisCompleted`` for ``result``."""
    event = DomainEvent.create(
        event_type=EVENT_TYPE,
        payload=build_payload(result),
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    get_event_bus().publish(event)
    logger.info(
        "pattern_analysis_completed_published",
        extra={
            "symbol": result.symbol,
            "run_id": str(result.id),
            "match_count": len(result.matched_patterns),
            "event_id": str(event.event_id),
        },
    )
    return event


__all__ = [
    "EVENT_TYPE",
    "build_payload",
    "publish_pattern_analysis_completed",
]
