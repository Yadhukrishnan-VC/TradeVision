from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from django.conf import settings

from apps.pattern_engine.domain.entities import (
    EvidenceItem,
    MatchedPattern,
    PatternAnalysisResult,
)
from apps.pattern_engine.domain.exceptions import PatternEngineError
from apps.pattern_engine.domain.similarity import (
    build_feature_vector,
    compute_similarity,
)
from apps.pattern_engine.domain.value_objects import FeatureVector, SimilarityScore
from apps.pattern_engine.infrastructure.repositories import (
    HistoricalFeatureVectorRepository,
    PatternAnalysisRunRepository,
)
from core.events.event_types import IntelligencePacket
from core.services import BaseService

logger = logging.getLogger(__name__)

SIX_DP = Decimal("0.000001")
FOUR_DP = Decimal("0.0001")


class PatternAnalysisService(BaseService):
    """Deterministic historical-session similarity analysis (ADR-007 §5).

    Orchestrates: feature vector construction from the IntelligencePacket →
    retrieval of precomputed historical vectors → weighted similarity scoring
    → analogue selection → enrichment (Trader Memory win rate, optional) →
    persistence of the rich result. Publication is handled separately by
    ``apps.pattern_engine.infrastructure.event_publisher``.

    The service never raises on missing optional data; it returns a result
    with empty matches and ``confidence_contribution == 0``. It raises
    ``PatternEngineError`` only when the packet failed freshness validation.
    """

    def __init__(
        self,
        vector_repository: HistoricalFeatureVectorRepository | None = None,
        run_repository: PatternAnalysisRunRepository | None = None,
    ) -> None:
        super().__init__()
        self._vector_repo = vector_repository or HistoricalFeatureVectorRepository()
        self._run_repo = run_repository or PatternAnalysisRunRepository()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        packet: IntelligencePacket,
        *,
        correlation_id: uuid.UUID,
    ) -> PatternAnalysisResult:
        """Run a full pattern analysis for ``packet``.

        Args:
            packet: A validated ``IntelligencePacket`` for a single symbol.
            correlation_id: UUID tracing this analysis to its origin.

        Returns:
            A persisted ``PatternAnalysisResult``.

        Raises:
            PatternEngineError: When ``packet.freshness_validated`` is False.
        """
        self._logger.info(
            "pe_analysis_started",
            extra={"symbol": packet.symbol, "correlation_id": str(correlation_id)},
        )

        if not packet.freshness_validated:
            raise PatternEngineError(
                "Pattern analysis rejected: packet failed freshness validation "
                f"for {packet.symbol}"
            )

        current_vector = self._build_current_vector(packet)
        historical = self._load_historical(packet.symbol, current_vector.as_of)

        if not historical:
            result = self._empty_result(
                symbol=packet.symbol,
                as_of=current_vector.as_of,
                note=(
                    "Insufficient historical data for similarity comparison "
                    "(no precomputed historical vectors found)."
                ),
            )
            self._persist(result, correlation_id)
            self._logger.info(
                "pe_analysis_empty_history",
                extra={"symbol": packet.symbol},
            )
            return result

        scored = self._score_analogues(current_vector, historical)
        self._logger.info(
            "pe_analogues_scored",
            extra={
                "symbol": packet.symbol,
                "scored": len(scored),
                "above_threshold": sum(
                    1 for p in scored if p.similarity.overall >= self._min_similarity
                ),
            },
        )

        top = scored[: self._top_n]

        historical_recommendation_accuracy = None
        if getattr(settings, "PATTERN_ENGINE_ACCURACY_LOOKUP_ENABLED", False):
            from apps.pattern_engine.infrastructure.accuracy_lookup import (
                get_historical_recommendation_accuracy,
            )

            try:
                historical_recommendation_accuracy = (
                    get_historical_recommendation_accuracy(packet.symbol)
                )
            except Exception:
                logger.exception(
                    "pe_accuracy_lookup_service_failed",
                    extra={"symbol": packet.symbol},
                )

        result = self._assemble_result(
            symbol=packet.symbol,
            as_of=current_vector.as_of,
            top_patterns=top,
            total_scored=len(scored),
            historical_recommendation_accuracy=historical_recommendation_accuracy,
        )
        self._persist(result, correlation_id)

        self._logger.info(
            "pe_analysis_completed",
            extra={
                "symbol": packet.symbol,
                "run_id": str(result.id),
                "match_count": len(result.matched_patterns),
                "confidence_contribution": str(result.confidence_contribution),
            },
        )
        return result

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def _build_current_vector(self, packet: IntelligencePacket) -> FeatureVector:
        return build_feature_vector(
            symbol=packet.symbol,
            as_of=packet.timestamp,
            price_context=packet.price_context,
            technical_context=packet.technical_context,
            breadth_context=packet.breadth_context,
            options_context=packet.options_context,
            global_context=packet.global_context,
        )

    def _load_historical(self, symbol: str, as_of: Any):
        return self._vector_repo.find_recent(
            symbol=symbol,
            before=as_of,
            limit=self._history_limit,
        )

    def _score_analogues(
        self,
        current: FeatureVector,
        historical,
    ) -> list[MatchedPattern]:
        scored: list[MatchedPattern] = []
        for row in historical:
            candidate = self._vector_repo.to_domain(row)
            score = compute_similarity(candidate, current, weights=self._weights)
            if score.overall < self._min_similarity:
                continue
            scored.append(self._to_matched_pattern(row, candidate, score))
        scored.sort(key=lambda p: p.similarity.overall, reverse=True)
        return scored

    def _to_matched_pattern(
        self,
        row,
        candidate: FeatureVector,
        score: SimilarityScore,
    ) -> MatchedPattern:
        outcome_pct = row.subsequent_price_change_pct
        window_hours = int(row.subsequent_window_hours or 24)
        date_str = candidate.as_of.date().isoformat()
        if outcome_pct is not None:
            outcome_summary = (
                f"On {date_str} the session moved {outcome_pct:+.2f}% in the "
                f"following session."
            )
        else:
            outcome_summary = (
                f"On {date_str} no subsequent outcome has been recorded yet."
            )
        return MatchedPattern(
            date_str=date_str,
            similarity=score,
            outcome_summary=outcome_summary,
            subsequent_price_change_pct=outcome_pct
            if outcome_pct is not None
            else Decimal(0),
            subsequent_window_hours=window_hours,
        )

    def _assemble_result(
        self,
        *,
        symbol: str,
        as_of: Any,
        top_patterns: list[MatchedPattern],
        total_scored: int,
        historical_recommendation_accuracy: Decimal | None,
    ) -> PatternAnalysisResult:
        run_id = uuid.uuid4()
        top = top_patterns[0] if top_patterns else None

        top_summary = self._top_analogue_summary(top)
        confidence = (
            self._confidence_contribution(top.similarity.overall)
            if top is not None
            else Decimal(0)
        )
        evidence = self._build_evidence(
            symbol=symbol,
            top_pattern=top,
            total_scored=total_scored,
            accuracy=historical_recommendation_accuracy,
        )
        note = (
            ""
            if top is not None
            else ("No historical session met the minimum similarity threshold.")
        )

        return PatternAnalysisResult(
            id=run_id,
            symbol=symbol.upper(),
            as_of=as_of,
            matched_patterns=tuple(top_patterns),
            top_analogue_summary=top_summary,
            historical_recommendation_accuracy=historical_recommendation_accuracy,
            confidence_contribution=confidence,
            evidence=tuple(evidence),
            data_sufficiency_note=note,
        )

    def _empty_result(
        self,
        *,
        symbol: str,
        as_of: Any,
        note: str,
    ) -> PatternAnalysisResult:
        return PatternAnalysisResult(
            id=uuid.uuid4(),
            symbol=symbol.upper(),
            as_of=as_of,
            matched_patterns=(),
            top_analogue_summary=(
                "No historical analogue available — insufficient precomputed history."
            ),
            historical_recommendation_accuracy=None,
            confidence_contribution=Decimal(0),
            evidence=(),
            data_sufficiency_note=note,
        )

    def _persist(
        self, result: PatternAnalysisResult, correlation_id: uuid.UUID
    ) -> None:
        self._run_repo.save_result(result)
        self._logger.info(
            "pe_run_persisted",
            extra={"run_id": str(result.id), "symbol": result.symbol},
        )

    # ------------------------------------------------------------------
    # Deterministic derivations
    # ------------------------------------------------------------------

    def _top_analogue_summary(self, top: MatchedPattern | None) -> str:
        if top is None:
            return (
                "No sufficiently similar historical session found — pattern "
                "context not attached."
            )
        change = top.subsequent_price_change_pct
        if change:
            return (
                f"Top analogue {top.date_str} at {top.similarity.overall:.3f} "
                f"similarity; the stock moved {change:+.2f}% over the following "
                f"{top.subsequent_window_hours}h window."
            )
        return (
            f"Top analogue {top.date_str} at {top.similarity.overall:.3f} "
            f"similarity; no outcome recorded yet."
        )

    def _confidence_contribution(self, top_similarity: Decimal) -> Decimal:
        """Map top similarity into a bounded [0.0, 0.5] confidence contribution.

        Deterministic linear ramp: ``min_similarity`` → 0.0, ``1.0`` → 0.5.
        """
        min_sim = self._min_similarity
        span = Decimal(1) - min_sim
        if span <= 0:
            return Decimal(0)
        scaled = (top_similarity - min_sim) / span
        scaled = max(Decimal(0), min(Decimal(1), scaled))
        return (scaled * Decimal("0.5")).quantize(FOUR_DP)

    def _build_evidence(
        self,
        *,
        symbol: str,
        top_pattern: MatchedPattern | None,
        total_scored: int,
        accuracy: Decimal | None,
    ) -> list[EvidenceItem]:
        items: list[EvidenceItem] = [
            EvidenceItem(
                description="Pattern engine ran deterministically",
                supporting_metric="symbol",
                value=symbol.upper(),
            ),
            EvidenceItem(
                description="Historical sessions evaluated",
                supporting_metric="sessions_scored",
                value=str(total_scored),
            ),
        ]
        if top_pattern is not None:
            items.append(
                EvidenceItem(
                    description="Top analogue similarity",
                    supporting_metric="overall_similarity",
                    value=str(top_pattern.similarity.overall),
                )
            )
        if accuracy is not None:
            items.append(
                EvidenceItem(
                    description="Historical recommendation win rate",
                    supporting_metric="win_rate",
                    value=str(accuracy),
                )
            )
        return items

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    @property
    def _top_n(self) -> int:
        return int(getattr(settings, "PATTERN_ENGINE_TOP_N", 5))

    @property
    def _min_similarity(self) -> Decimal:
        return Decimal(str(getattr(settings, "PATTERN_ENGINE_MIN_SIMILARITY", "0.60")))

    @property
    def _history_limit(self) -> int:
        return int(getattr(settings, "PATTERN_ENGINE_HISTORY_LIMIT", 500))

    @property
    def _weights(self):
        from apps.pattern_engine.domain.similarity import DEFAULT_WEIGHTS

        return DEFAULT_WEIGHTS


__all__ = ["PatternAnalysisService"]
