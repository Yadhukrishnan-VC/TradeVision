from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from apps.pattern_engine.domain.entities import (
    EvidenceItem,
    MatchedPattern,
    PatternAnalysisResult,
)
from apps.pattern_engine.domain.value_objects import SimilarityScore
from apps.pattern_engine.infrastructure.event_publisher import (
    EVENT_TYPE,
    build_payload,
    publish_pattern_analysis_completed,
)

TZ = timezone.utc


def _result() -> PatternAnalysisResult:
    score = SimilarityScore(
        overall=Decimal("0.82"),
        feature_distance=Decimal("0.18"),
        per_group_distance={
            "price_action": Decimal("0.1"),
            "technical_state": Decimal("0.2"),
        },
    )
    pattern = MatchedPattern(
        date_str="2024-03-17",
        similarity=score,
        outcome_summary="On 2024-03-17 the session moved +2.10% in the following session.",
        subsequent_price_change_pct=Decimal("2.10"),
        subsequent_window_hours=24,
    )
    return PatternAnalysisResult(
        id=uuid.uuid4(),
        symbol="RELIANCE",
        as_of=datetime(2024, 3, 18, 10, 0, tzinfo=TZ),
        matched_patterns=(pattern,),
        top_analogue_summary="Top analogue 2024-03-17 at 0.820 similarity.",
        historical_recommendation_accuracy=Decimal("0.65"),
        confidence_contribution=Decimal("0.275"),
        evidence=(
            EvidenceItem(
                description="Top analogue similarity",
                supporting_metric="overall_similarity",
                value="0.82",
            ),
        ),
    )


class TestBuildPayload:
    def test_frozen_contract_keys_present(self) -> None:
        payload = build_payload(_result())
        assert payload["symbol"] == "RELIANCE"
        assert isinstance(payload["similar_dates"], list)
        first = payload["similar_dates"][0]
        assert first["date_str"] == "2024-03-17"
        assert first["similarity_score"] == "0.82"
        assert first["outcome_summary"] == (
            "On 2024-03-17 the session moved +2.10% in the following session."
        )
        assert payload["top_analogue_summary"] == (
            "Top analogue 2024-03-17 at 0.820 similarity."
        )

    def test_additive_keys_present(self) -> None:
        payload = build_payload(_result())
        assert payload["run_id"]
        assert payload["feature_distance"] == "0.18"
        assert payload["per_group_distance"] == {
            "price_action": "0.1",
            "technical_state": "0.2",
        }
        assert payload["historical_recommendation_accuracy"] == "0.65"
        assert payload["confidence_contribution"] == "0.275"
        assert payload["evidence"][0]["description"] == "Top analogue similarity"
        assert len(payload["matching_patterns"]) == 1

    def test_empty_result(self) -> None:
        result = PatternAnalysisResult(
            id=uuid.uuid4(),
            symbol="TCS",
            as_of=datetime(2024, 3, 18, 10, 0, tzinfo=TZ),
            matched_patterns=(),
            top_analogue_summary="No analogue.",
            historical_recommendation_accuracy=None,
            confidence_contribution=Decimal(0),
            evidence=(),
            data_sufficiency_note="No history.",
        )
        payload = build_payload(result)
        assert payload["similar_dates"] == []
        assert payload["feature_distance"] is None
        assert payload["historical_recommendation_accuracy"] is None


class TestPublish:
    def test_publishes_event_with_expected_type(self) -> None:
        result = _result()
        correlation_id = uuid.uuid4()
        with patch(
            "apps.pattern_engine.infrastructure.event_publisher.get_event_bus"
        ) as mock_get_bus:
            bus = mock_get_bus.return_value
            event = publish_pattern_analysis_completed(
                result,
                correlation_id=correlation_id,
                causation_id=uuid.uuid4(),
            )
        assert event.event_type == EVENT_TYPE
        assert event.correlation_id == correlation_id
        bus.publish.assert_called_once_with(event)
