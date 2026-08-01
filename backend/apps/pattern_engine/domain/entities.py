from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from apps.pattern_engine.domain.value_objects import (
    EvidenceItem,
    SimilarityScore,
)


@dataclass(frozen=True)
class MatchedPattern:
    """One retrieved historical analogue.

    ``outcome_summary`` maps 1:1 to the frozen ``PatternMatch.outcome_summary``
    contract consumed by ``apps.intelligence`` — it must stay a short,
    deterministic, human-readable string.
    """

    date_str: str
    similarity: SimilarityScore
    outcome_summary: str
    subsequent_price_change_pct: Decimal
    subsequent_window_hours: int


@dataclass(frozen=True)
class SimilarSession:
    """Alias-level grouping when multiple timeframes matched the same date.

    Kept separate from ``MatchedPattern`` so the API can expose per-timeframe
    detail without overloading the event contract.
    """

    matched_patterns: tuple[MatchedPattern, ...]
    dominant_similarity: SimilarityScore


@dataclass(frozen=True)
class PatternAnalysisResult:
    """Rich internal result of a Pattern Engine analysis run.

    This is the Pattern Engine's own domain object — NOT the same class as
    ``core.events.event_types.PatternContext``. It is mapped down to that
    narrower, frozen contract at publication time (see
    ``infrastructure.event_publisher``).
    """

    id: uuid.UUID
    symbol: str
    as_of: datetime
    matched_patterns: tuple[MatchedPattern, ...]
    top_analogue_summary: str
    historical_recommendation_accuracy: Decimal | None
    confidence_contribution: Decimal
    evidence: tuple[EvidenceItem, ...]
    data_sufficiency_note: str = ""


__all__ = [
    "EvidenceItem",
    "MatchedPattern",
    "PatternAnalysisResult",
    "SimilarSession",
]
