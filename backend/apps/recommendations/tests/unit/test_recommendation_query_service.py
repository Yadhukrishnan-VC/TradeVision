from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.recommendations.application.recommendation_query_service import RecommendationQueryService
from apps.recommendations.domain.entities import RecommendationAggregate, RecommendationStatus
from apps.recommendations.domain.exceptions import RecommendationNotFound
from apps.recommendations.infrastructure.models import Recommendation
from apps.recommendations.infrastructure.repositories import RecommendationRepository


@pytest.fixture
def repository_mock() -> MagicMock:
    return MagicMock(spec=RecommendationRepository)


@pytest.fixture
def service_with_mock(repository_mock) -> RecommendationQueryService:
    service = RecommendationQueryService()
    service._repository = repository_mock
    return service


def _make_rec(
    recommendation_id: uuid.UUID,
    symbol: str = "RELIANCE",
    direction: str = "BUY",
    status: str = RecommendationStatus.DRAFT,
) -> Recommendation:
    rec = MagicMock(spec=Recommendation)
    rec.id = recommendation_id
    rec.symbol = symbol
    rec.direction = direction
    rec.status = status
    rec.confidence_score = Decimal("0.85")
    rec.analysis_event_id = None
    rec.rule_execution_id = None
    rec.rule_execution_id_id = None
    rec.strategy_id = None
    rec.confidence_evaluation_id = None
    rec.published_at = None
    rec.created_at = None
    return rec


class TestRecommendationQueryService:
    def test_get_recommendation_returns_aggregate(self, service_with_mock, repository_mock, recommendation_id) -> None:
        rec = _make_rec(recommendation_id)
        repository_mock.get_by_id.return_value = rec

        aggregate = service_with_mock.get_recommendation(recommendation_id)

        assert isinstance(aggregate, RecommendationAggregate)
        assert aggregate.id == recommendation_id
        assert aggregate.symbol == "RELIANCE"
        repository_mock.get_by_id.assert_called_once_with(recommendation_id)

    def test_get_recommendation_not_found_raises(self, service_with_mock, repository_mock) -> None:
        repository_mock.get_by_id.return_value = None

        with pytest.raises(RecommendationNotFound):
            service_with_mock.get_recommendation(uuid.uuid4())

    def test_list_recommendations_returns_aggregates(self, service_with_mock, repository_mock, recommendation_id) -> None:
        rec = _make_rec(recommendation_id)
        repository_mock.list.return_value = [rec]

        results = service_with_mock.list_recommendations()

        assert len(results) == 1
        assert isinstance(results[0], RecommendationAggregate)
        assert results[0].id == recommendation_id

    def test_list_with_filters_passes_to_repository(self, service_with_mock, repository_mock) -> None:
        repository_mock.list.return_value = []

        service_with_mock.list_recommendations(symbol="TCS", status="PUBLISHED", direction="SELL")

        repository_mock.list.assert_called_once_with(symbol="TCS", status="PUBLISHED", direction="SELL")

    def test_list_without_filters_calls_list_empty(self, service_with_mock, repository_mock) -> None:
        repository_mock.list.return_value = []

        service_with_mock.list_recommendations()

        repository_mock.list.assert_called_once_with()

    def test_list_respects_offset_and_limit(self, service_with_mock, repository_mock, recommendation_id) -> None:
        ids = [uuid.uuid4() for _ in range(5)]
        recs = [_make_rec(rid) for rid in ids]
        repository_mock.list.return_value = recs

        results = service_with_mock.list_recommendations(offset=1, limit=2)

        assert len(results) == 2
        assert results[0].id == ids[1]
        assert results[1].id == ids[2]

    def test_list_empty_returns_empty_list(self, service_with_mock, repository_mock) -> None:
        repository_mock.list.return_value = []

        results = service_with_mock.list_recommendations()

        assert results == []

    def test_list_with_only_symbol_filter(self, service_with_mock, repository_mock) -> None:
        repository_mock.list.return_value = []

        service_with_mock.list_recommendations(symbol="TCS")

        repository_mock.list.assert_called_once_with(symbol="TCS")

    def test_list_with_only_status_filter(self, service_with_mock, repository_mock) -> None:
        repository_mock.list.return_value = []

        service_with_mock.list_recommendations(status="PUBLISHED")

        repository_mock.list.assert_called_once_with(status="PUBLISHED")

    def test_list_with_only_direction_filter(self, service_with_mock, repository_mock) -> None:
        repository_mock.list.return_value = []

        service_with_mock.list_recommendations(direction="SELL")

        repository_mock.list.assert_called_once_with(direction="SELL")
