from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.recommendations.domain.entities import RecommendationStatus
from apps.recommendations.infrastructure.models import Recommendation, RecommendationStatusHistory

pytestmark = pytest.mark.django_db


class TestRecommendationLifecycle:
    def _reset_bus(self):
        from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus, get_event_bus
        reset_event_bus()
        return get_event_bus()

    def test_full_lifecycle_create_to_accepted(self, symbol, direction, confidence_score) -> None:
        bus = self._reset_bus()
        from apps.recommendations.application.recommendation_command_service import RecommendationCommandService
        service = RecommendationCommandService()

        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )

        saved = Recommendation.objects.get(id=aggregate.id)
        assert saved.status == RecommendationStatus.DRAFT
        assert saved.symbol == symbol

        published = service.publish_recommendation(aggregate.id)
        assert published.status == RecommendationStatus.PUBLISHED

        saved.refresh_from_db()
        assert saved.status == RecommendationStatus.PUBLISHED
        assert saved.published_at is not None

        accepted = service.accept_recommendation(aggregate.id, reason="good analysis", changed_by="trader")
        assert accepted.status == RecommendationStatus.ACCEPTED

        saved.refresh_from_db()
        assert saved.status == RecommendationStatus.ACCEPTED

        history = RecommendationStatusHistory.objects.filter(recommendation_id=aggregate.id).order_by("created_at")
        assert history.count() == 2
        assert history[0].from_status == RecommendationStatus.DRAFT
        assert history[0].to_status == RecommendationStatus.PUBLISHED
        assert history[0].reason == "auto-publish"
        assert history[0].changed_by == "system"
        assert history[1].from_status == RecommendationStatus.PUBLISHED
        assert history[1].to_status == RecommendationStatus.ACCEPTED
        assert history[1].reason == "good analysis"
        assert history[1].changed_by == "trader"

        published_types = [e.event_type for e in bus.published_events]
        assert "recommendations.RecommendationCreated" in published_types
        assert "recommendations.RecommendationStatusChanged" in published_types

    def test_full_lifecycle_create_to_rejected(self, symbol, direction, confidence_score) -> None:
        bus = self._reset_bus()
        from apps.recommendations.application.recommendation_command_service import RecommendationCommandService
        service = RecommendationCommandService()

        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        service.publish_recommendation(aggregate.id)
        service.reject_recommendation(aggregate.id, reason="unfavorable market")

        saved = Recommendation.objects.get(id=aggregate.id)
        assert saved.status == RecommendationStatus.REJECTED

        history = RecommendationStatusHistory.objects.filter(recommendation_id=aggregate.id)
        assert history.count() == 2
        assert history.last().to_status == RecommendationStatus.REJECTED
        assert history.last().reason == "unfavorable market"

    def test_full_lifecycle_create_to_expired(self, symbol, direction, confidence_score) -> None:
        bus = self._reset_bus()
        from apps.recommendations.application.recommendation_command_service import RecommendationCommandService
        service = RecommendationCommandService()

        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        service.publish_recommendation(aggregate.id)
        service.expire_recommendation(aggregate.id)

        saved = Recommendation.objects.get(id=aggregate.id)
        assert saved.status == RecommendationStatus.EXPIRED

        history = RecommendationStatusHistory.objects.filter(recommendation_id=aggregate.id)
        assert history.count() == 2
        assert history.last().to_status == RecommendationStatus.EXPIRED

    def test_events_published_on_each_transition(self, symbol, direction, confidence_score) -> None:
        bus = self._reset_bus()
        from apps.recommendations.application.recommendation_command_service import RecommendationCommandService
        service = RecommendationCommandService()

        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )

        bus.clear()
        service.publish_recommendation(aggregate.id)
        assert len(bus.published_events) == 1
        assert bus.published_events[0].event_type == "recommendations.RecommendationStatusChanged"

        bus.clear()
        service.accept_recommendation(aggregate.id)
        assert len(bus.published_events) == 1
        assert bus.published_events[0].event_type == "recommendations.RecommendationStatusChanged"

    def test_created_event_has_full_payload(self, symbol, direction, confidence_score) -> None:
        bus = self._reset_bus()
        from apps.recommendations.application.recommendation_command_service import RecommendationCommandService
        service = RecommendationCommandService()

        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )

        created_event = next(e for e in bus.published_events if e.event_type == "recommendations.RecommendationCreated")
        assert created_event.payload["recommendation_id"] == str(aggregate.id)
        assert created_event.payload["symbol"] == symbol
        assert created_event.payload["direction"] == direction
        assert created_event.payload["confidence_score"] == "0.85"
        assert created_event.payload["status"] == RecommendationStatus.DRAFT
        assert created_event.correlation_id == aggregate.id

    def test_status_changed_event_has_transition_details(self, symbol, direction, confidence_score) -> None:
        bus = self._reset_bus()
        from apps.recommendations.application.recommendation_command_service import RecommendationCommandService
        service = RecommendationCommandService()

        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        bus.clear()
        service.accept_recommendation(
            service.publish_recommendation(aggregate.id).id,
            reason="solid",
            changed_by="analyst",
        )

        status_event = next(e for e in bus.published_events if e.event_type == "recommendations.RecommendationStatusChanged")
        assert status_event.payload["from_status"] == RecommendationStatus.PUBLISHED
        assert status_event.payload["to_status"] == RecommendationStatus.ACCEPTED
        assert status_event.correlation_id == aggregate.id

    def test_illegal_transition_does_not_persist_or_publish(self, symbol, direction, confidence_score) -> None:
        bus = self._reset_bus()
        from apps.recommendations.application.recommendation_command_service import RecommendationCommandService
        from apps.recommendations.domain.exceptions import IllegalTransition
        service = RecommendationCommandService()

        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        bus.clear()

        with pytest.raises(IllegalTransition):
            service.accept_recommendation(aggregate.id)

        saved = Recommendation.objects.get(id=aggregate.id)
        assert saved.status == RecommendationStatus.DRAFT
        assert len(bus.published_events) == 0

    def test_multiple_recommendations_independent(self, symbol, confidence_score) -> None:
        bus = self._reset_bus()
        from apps.recommendations.application.recommendation_command_service import RecommendationCommandService
        service = RecommendationCommandService()

        agg1 = service.create_from_ai_response(symbol=symbol, direction="BUY", confidence_score=confidence_score)
        agg2 = service.create_from_ai_response(symbol=symbol, direction="SELL", confidence_score=confidence_score)

        service.publish_recommendation(agg1.id)
        service.reject_recommendation(agg1.id)

        service.publish_recommendation(agg2.id)
        service.accept_recommendation(agg2.id)

        r1 = Recommendation.objects.get(id=agg1.id)
        r2 = Recommendation.objects.get(id=agg2.id)
        assert r1.status == RecommendationStatus.REJECTED
        assert r2.status == RecommendationStatus.ACCEPTED

        hist1 = RecommendationStatusHistory.objects.filter(recommendation_id=agg1.id)
        hist2 = RecommendationStatusHistory.objects.filter(recommendation_id=agg2.id)
        assert hist1.count() == 2
        assert hist2.count() == 2

    def test_status_history_records_changed_by_and_reason(self, symbol, direction, confidence_score) -> None:
        bus = self._reset_bus()
        from apps.recommendations.application.recommendation_command_service import RecommendationCommandService
        service = RecommendationCommandService()

        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )
        service.publish_recommendation(aggregate.id)
        service.reject_recommendation(aggregate.id, reason="high_risk", changed_by="risk_manager")

        history = RecommendationStatusHistory.objects.filter(recommendation_id=aggregate.id).order_by("created_at")
        assert history[1].changed_by == "risk_manager"
        assert history[1].reason == "high_risk"

    def test_query_service_returns_created_recommendation(self, symbol, direction, confidence_score) -> None:
        bus = self._reset_bus()
        from apps.recommendations.application.recommendation_command_service import RecommendationCommandService
        from apps.recommendations.application.recommendation_query_service import RecommendationQueryService
        cmd_service = RecommendationCommandService()
        query_service = RecommendationQueryService()

        aggregate = cmd_service.create_from_ai_response(
            symbol=symbol,
            direction=direction,
            confidence_score=confidence_score,
        )

        fetched = query_service.get_recommendation(aggregate.id)
        assert fetched.id == aggregate.id
        assert fetched.status == RecommendationStatus.DRAFT

        cmd_service.publish_recommendation(aggregate.id)
        fetched = query_service.get_recommendation(aggregate.id)
        assert fetched.status == RecommendationStatus.PUBLISHED

    def test_query_service_lists_recommendations_with_filters(self, symbol, confidence_score) -> None:
        bus = self._reset_bus()
        from apps.recommendations.application.recommendation_command_service import RecommendationCommandService
        from apps.recommendations.application.recommendation_query_service import RecommendationQueryService
        cmd_service = RecommendationCommandService()
        query_service = RecommendationQueryService()

        agg1 = cmd_service.create_from_ai_response(symbol=symbol, direction="BUY", confidence_score=confidence_score)
        agg2 = cmd_service.create_from_ai_response(symbol="TCS", direction="SELL", confidence_score=Decimal("0.60"))

        results = query_service.list_recommendations(symbol=symbol)
        assert len(results) == 1
        assert results[0].id == agg1.id

        results = query_service.list_recommendations(symbol="TCS")
        assert len(results) == 1
        assert results[0].id == agg2.id

        results = query_service.list_recommendations()
        assert len(results) == 2
