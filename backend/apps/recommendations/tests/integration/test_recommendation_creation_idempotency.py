"""
Batch REC-1 — create_recommendation task delivery idempotency.

Dispatching ``create_recommendation`` twice with the same ``analysis_event_id``
must persist a single recommendation and only compose the explanation once
(``compose_explanation`` is not idempotent because
``RecommendationExplanation.recommendation_id`` is unique).
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from apps.recommendations.infrastructure.models import Recommendation

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _reset_event_bus():
    from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus

    reset_event_bus()


def test_double_dispatch_persists_single_row(symbol, direction) -> None:
    from apps.recommendations.infrastructure.tasks import create_recommendation

    analysis_event_id = str(uuid.uuid4())

    with patch("apps.recommendations.infrastructure.tasks.compose_explanation.delay") as mock_compose:
        first = create_recommendation(
            symbol=symbol,
            direction=direction,
            confidence_score="0.80",
            analysis_event_id=analysis_event_id,
        )
        second = create_recommendation(
            symbol=symbol,
            direction=direction,
            confidence_score="0.80",
            analysis_event_id=analysis_event_id,
        )

    assert first["recommendation_id"] == second["recommendation_id"]
    assert Recommendation.objects.count() == 1
    assert mock_compose.call_count == 1


def test_single_dispatch_composes_explanation(symbol, direction) -> None:
    from apps.recommendations.infrastructure.tasks import create_recommendation

    with patch("apps.recommendations.infrastructure.tasks.compose_explanation.delay") as mock_compose:
        create_recommendation(
            symbol=symbol,
            direction=direction,
            confidence_score="0.80",
            analysis_event_id=str(uuid.uuid4()),
        )

    mock_compose.assert_called_once()