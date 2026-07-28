from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.recommendations.application.recommendation_command_service import RecommendationCommandService
from apps.recommendations.domain.entities import RecommendationAggregate, RecommendationStatus
from apps.recommendations.domain.exceptions import IllegalTransition, RecommendationNotFound
from apps.recommendations.infrastructure.models import Recommendation

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _reset_event_bus():
    from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus
    reset_event_bus()


class TestRecommendationCommandService:
    def test_create_from_ai_response_returns_aggregate(self, symbol, direction, confidence_score) -> None:
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        assert aggregate.status == RecommendationStatus.DRAFT
        assert aggregate.symbol == symbol
        assert aggregate.direction == direction
        assert aggregate.confidence_score == confidence_score

    def test_create_persists_to_database(self, symbol, direction, confidence_score) -> None:
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        saved = Recommendation.objects.get(id=aggregate.id)
        assert saved.status == RecommendationStatus.DRAFT
        assert saved.symbol == symbol

    def test_create_publishes_event(self, symbol, direction, confidence_score) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        bus = get_event_bus()
        published_types = [e.event_type for e in bus.published_events]
        assert "recommendations.RecommendationCreated" in published_types
        created_event = next(e for e in bus.published_events if e.event_type == "recommendations.RecommendationCreated")
        assert created_event.payload["recommendation_id"] == str(aggregate.id)
        assert created_event.payload["symbol"] == symbol

    def test_publish_recommendation_transitions_status(self, symbol, direction, confidence_score) -> None:
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        published = service.publish_recommendation(aggregate.id)
        assert published.status == RecommendationStatus.PUBLISHED
        assert published.published_at is not None

    def test_publish_updates_database(self, symbol, direction, confidence_score) -> None:
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        service.publish_recommendation(aggregate.id)
        saved = Recommendation.objects.get(id=aggregate.id)
        assert saved.status == RecommendationStatus.PUBLISHED
        assert saved.published_at is not None

    def test_publish_creates_status_history(self, symbol, direction, confidence_score) -> None:
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        service.publish_recommendation(aggregate.id)
        from apps.recommendations.infrastructure.models import RecommendationStatusHistory
        history = RecommendationStatusHistory.objects.filter(recommendation_id=aggregate.id)
        assert history.count() == 1
        entry = history.first()
        assert entry.from_status == RecommendationStatus.DRAFT
        assert entry.to_status == RecommendationStatus.PUBLISHED

    def test_publish_publishes_status_changed_event(self, symbol, direction, confidence_score) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        bus = get_event_bus()
        bus.clear()
        service.publish_recommendation(aggregate.id)
        published_types = [e.event_type for e in bus.published_events]
        assert "recommendations.RecommendationStatusChanged" in published_types

    def test_accept_recommendation_transitions_status(self, symbol, direction, confidence_score) -> None:
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        service.publish_recommendation(aggregate.id)
        accepted = service.accept_recommendation(aggregate.id, reason="good setup", changed_by="trader")
        assert accepted.status == RecommendationStatus.ACCEPTED

    def test_accept_creates_status_history(self, symbol, direction, confidence_score) -> None:
        from apps.recommendations.infrastructure.models import RecommendationStatusHistory
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        service.publish_recommendation(aggregate.id)
        service.accept_recommendation(aggregate.id, reason="good setup", changed_by="trader")
        history = RecommendationStatusHistory.objects.filter(recommendation_id=aggregate.id)
        assert history.count() == 2
        last = history.last()
        assert last.from_status == RecommendationStatus.PUBLISHED
        assert last.to_status == RecommendationStatus.ACCEPTED
        assert last.reason == "good setup"
        assert last.changed_by == "trader"

    def test_reject_recommendation_transitions_status(self, symbol, direction, confidence_score) -> None:
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        service.publish_recommendation(aggregate.id)
        rejected = service.reject_recommendation(aggregate.id, reason="bad risk")
        assert rejected.status == RecommendationStatus.REJECTED

    def test_expire_recommendation_transitions_status(self, symbol, direction, confidence_score) -> None:
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        service.publish_recommendation(aggregate.id)
        expired = service.expire_recommendation(aggregate.id)
        assert expired.status == RecommendationStatus.EXPIRED

    def test_expire_defaults_reason_and_changed_by(self, symbol, direction, confidence_score) -> None:
        from apps.recommendations.infrastructure.models import RecommendationStatusHistory
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        service.publish_recommendation(aggregate.id)
        service.expire_recommendation(aggregate.id)
        history = RecommendationStatusHistory.objects.filter(recommendation_id=aggregate.id)
        last = history.last()
        assert last.reason == "timeout"
        assert last.changed_by == "system"

    def test_publish_on_draft_creates_status_history(self, symbol, direction, confidence_score) -> None:
        from apps.recommendations.infrastructure.models import RecommendationStatusHistory
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        service.publish_recommendation(aggregate.id)
        history = RecommendationStatusHistory.objects.filter(recommendation_id=aggregate.id)
        assert history.count() == 1
        entry = history.first()
        assert entry.reason == "auto-publish"
        assert entry.changed_by == "system"

    def test_publish_on_nonexistent_raises_recommendation_not_found(self) -> None:
        service = RecommendationCommandService()
        with pytest.raises(RecommendationNotFound):
            service.publish_recommendation(uuid.uuid4())

    def test_accept_on_nonexistent_raises_recommendation_not_found(self) -> None:
        service = RecommendationCommandService()
        with pytest.raises(RecommendationNotFound):
            service.accept_recommendation(uuid.uuid4())

    def test_reject_on_nonexistent_raises_recommendation_not_found(self) -> None:
        service = RecommendationCommandService()
        with pytest.raises(RecommendationNotFound):
            service.reject_recommendation(uuid.uuid4())

    def test_expire_on_nonexistent_raises_recommendation_not_found(self) -> None:
        service = RecommendationCommandService()
        with pytest.raises(RecommendationNotFound):
            service.expire_recommendation(uuid.uuid4())

    def test_accept_draft_raises_illegal_transition(self, symbol, direction, confidence_score) -> None:
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        with pytest.raises(IllegalTransition):
            service.accept_recommendation(aggregate.id)

    def test_reject_draft_raises_illegal_transition(self, symbol, direction, confidence_score) -> None:
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        with pytest.raises(IllegalTransition):
            service.reject_recommendation(aggregate.id)

    def test_expire_draft_raises_illegal_transition(self, symbol, direction, confidence_score) -> None:
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        with pytest.raises(IllegalTransition):
            service.expire_recommendation(aggregate.id)

    def test_double_accept_raises_illegal_transition(self, symbol, direction, confidence_score) -> None:
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        service.publish_recommendation(aggregate.id)
        service.accept_recommendation(aggregate.id)
        with pytest.raises(IllegalTransition):
            service.accept_recommendation(aggregate.id)

    def test_accept_publishes_status_changed_event(self, symbol, direction, confidence_score) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        service.publish_recommendation(aggregate.id)
        bus = get_event_bus()
        bus.clear()
        service.accept_recommendation(aggregate.id)
        published_types = [e.event_type for e in bus.published_events]
        assert "recommendations.RecommendationStatusChanged" in published_types
        event = next(e for e in bus.published_events if e.event_type == "recommendations.RecommendationStatusChanged")
        assert event.payload["from_status"] == RecommendationStatus.PUBLISHED
        assert event.payload["to_status"] == RecommendationStatus.ACCEPTED

    def test_reject_publishes_status_changed_event(self, symbol, direction, confidence_score) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        service.publish_recommendation(aggregate.id)
        bus = get_event_bus()
        bus.clear()
        service.reject_recommendation(aggregate.id)
        published_types = [e.event_type for e in bus.published_events]
        assert "recommendations.RecommendationStatusChanged" in published_types

    def test_expire_publishes_status_changed_event(self, symbol, direction, confidence_score) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        service.publish_recommendation(aggregate.id)
        bus = get_event_bus()
        bus.clear()
        service.expire_recommendation(aggregate.id)
        published_types = [e.event_type for e in bus.published_events]
        assert "recommendations.RecommendationStatusChanged" in published_types
