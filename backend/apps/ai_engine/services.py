from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceResult:
    raw_confidence: float
    adjusted_confidence: float
    threshold_met: bool
    adjustment_reasons: list[str] = field(default_factory=list)
    confidence_evaluation_id: str | None = None


class ConfidenceEngine:
    def evaluate(
        self,
        raw_confidence: float,
        strategy: Any = None,
        packet: Any = None,
    ) -> ConfidenceResult:
        adjusted = raw_confidence
        reasons: list[str] = []

        threshold_met = True
        if strategy is not None:
            threshold = float(
                getattr(strategy, "confidence_threshold", settings.AI_CONFIDENCE_FLOOR)
            )
            if adjusted < threshold:
                threshold_met = False
                reasons.append(
                    f"confidence {adjusted:.4f} below strategy threshold {threshold:.4f}"
                )

        if packet is not None:
            data_quality = getattr(packet, "data_quality", None)
            if data_quality is not None:
                quality_score = getattr(data_quality, "quality_score", 1.0)
                if quality_score < settings.INTELLIGENCE_MIN_QUALITY_SCORE:
                    penalty = (settings.INTELLIGENCE_MIN_QUALITY_SCORE - quality_score) * 0.5
                    adjusted = max(0.0, adjusted - penalty)
                    reasons.append(
                        f"data quality penalty: score={quality_score:.2f}, "
                        f"penalty={penalty:.4f}"
                    )

                missing = getattr(data_quality, "missing_sources", ())
                if missing:
                    reasons.append(
                        f"missing data sources: {', '.join(missing)}"
                    )
                    adjusted = max(0.0, adjusted - 0.05 * len(missing))

            portfolio_context = getattr(packet, "portfolio_context", None)
            if portfolio_context is None:
                reasons.append("portfolio context missing")
                adjusted = max(0.0, adjusted - 0.03)

            risk_context = getattr(packet, "risk_context", None)
            if risk_context is None:
                reasons.append("risk context missing")
                adjusted = max(0.0, adjusted - 0.03)

        adjusted = round(max(0.0, min(1.0, adjusted)), 4)

        return ConfidenceResult(
            raw_confidence=raw_confidence,
            adjusted_confidence=adjusted,
            threshold_met=threshold_met,
            adjustment_reasons=reasons,
        )

    def evaluate_and_persist(
        self,
        raw_confidence: float,
        packet_id: str,
        strategy: Any = None,
        packet: Any = None,
    ) -> ConfidenceResult:
        result = self.evaluate(
            raw_confidence=raw_confidence,
            strategy=strategy,
            packet=packet,
        )

        from apps.ai_engine.models import ConfidenceEvaluation

        try:
            obj = ConfidenceEvaluation.objects.create(
                packet_id=packet_id,
                raw_confidence=result.raw_confidence,
                adjusted_confidence=result.adjusted_confidence,
                threshold_met=result.threshold_met,
                adjustment_reasons=result.adjustment_reasons,
                strategy=strategy if strategy and hasattr(strategy, "id") else None,
            )
            result.confidence_evaluation_id = str(obj.id)
        except Exception:
            logger.exception(
                "confidence_evaluation_persist_failed",
                extra={"packet_id": packet_id},
            )

        return result
