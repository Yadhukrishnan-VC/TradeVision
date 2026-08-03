"""
Batch REC-1 — Idempotent recommendation creation.

``Recommendation.analysis_event_id`` is unique, so a duplicate invocation of
:meth:`RecommendationCommandService.create_from_ai_response` for the same
analysis event must:
    - return the already-persisted row (never raise),
    - not publish a second ``RecommendationCreated`` event,
mirroring the ``RuleExecution.create_from_firing()`` idiom.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.test import override_settings

from apps.recommendations.infrastructure.models import Recommendation

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _reset_event_bus():
    from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus

    reset_event_bus()


def _service():
    from apps.recommendations.application.recommendation_command_service import (
        RecommendationCommandService,
    )

    return RecommendationCommandService()


def _created_published(service) -> int:
    from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

    bus = get_event_bus()
    return sum(
        1 for e in bus.published_events if e.event_type == "recommendations.RecommendationCreated"
    )


class TestIdempotentCreateFromAiResponse:
    @override_settings(EVENT_BUS_IMPLEMENTATION="fake")
    def test_duplicate_analysis_event_returns_existing_id(
        self, symbol, direction, confidence_score
    ) -> None:
        service = _service()
        analysis_event_id = uuid.uuid4()

        first = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
            analysis_event_id=analysis_event_id,
        )
        second = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
            analysis_event_id=analysis_event_id,
        )

        assert second.id == first.id
        assert Recommendation.objects.count() == 1

    @override_settings(EVENT_BUS_IMPLEMENTATION="fake")
    def test_duplicate_does_not_publish_created_twice(self, symbol, direction, confidence_score) -> None:
        service = _service()
        analysis_event_id = uuid.uuid4()

        service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
            analysis_event_id=analysis_event_id,
        )
        service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
            analysis_event_id=analysis_event_id,
        )

        assert _created_published(service) == 1

    @override_settings(EVENT_BUS_IMPLEMENTATION="fake")
    def test_duplicate_preserves_original_row(self, symbol, direction, confidence_score) -> None:
        service = _service()
        analysis_event_id = uuid.uuid4()
        provider = "deepseek"
        correlation_id = uuid.uuid4()

        service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
            analysis_event_id=analysis_event_id,
            provider=provider,
            correlation_id=correlation_id,
        )
        returned = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=Decimal("0.95"),
            analysis_event_id=analysis_event_id,
        )

        saved = Recommendation.objects.get(id=returned.id)
        assert saved.provider == provider
        assert saved.correlation_id == correlation_id
        assert str(saved.confidence_score) == str(confidence_score)

    @override_settings(EVENT_BUS_IMPLEMENTATION="fake")
    def test_multiple_none_analysis_events_create_distinct_rows(self, symbol, direction, confidence_score) -> None:
        service = _service()

        first = service.create_from_ai_response(
            symbol=symbol, direction=direction, confidence_score=confidence_score
        )
        second = service.create_from_ai_response(
            symbol=symbol, direction=direction, confidence_score=confidence_score
        )

        assert first.id != second.id
        assert Recommendation.objects.count() == 2

    @override_settings(EVENT_BUS_IMPLEMENTATION="fake")
    def test_non_duplicate_validation_error_propagates(self, symbol, direction) -> None:
        service = _service()
        analysis_event_id = uuid.uuid4()

        with pytest.raises(Exception, match="no more than 5 digits"):
            service.create_from_ai_response(
                symbol=symbol,
                direction=direction,
                confidence_score=Decimal("99999.99"),
                analysis_event_id=analysis_event_id,
            )

        assert Recommendation.objects.count() == 0