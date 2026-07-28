from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.recommendations.domain.entities import RecommendationAggregate, RecommendationStatus


@pytest.fixture
def recommendation_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def symbol() -> str:
    return "RELIANCE"


@pytest.fixture
def direction() -> str:
    return "BUY"


@pytest.fixture
def confidence_score() -> Decimal:
    return Decimal("0.85")


@pytest.fixture
def draft_aggregate(recommendation_id, symbol, direction, confidence_score) -> RecommendationAggregate:
    return RecommendationAggregate(
        id=recommendation_id,
        symbol=symbol,
        direction=direction,
        confidence_score=confidence_score,
        status=RecommendationStatus.DRAFT,
        analysis_event_id=None,
        rule_execution_id=None,
        strategy_id=None,
        confidence_evaluation_id=None,
        published_at=None,
    )


@pytest.fixture
def published_aggregate(recommendation_id, symbol, direction, confidence_score) -> RecommendationAggregate:
    return RecommendationAggregate(
        id=recommendation_id,
        symbol=symbol,
        direction=direction,
        confidence_score=confidence_score,
        status=RecommendationStatus.PUBLISHED,
        analysis_event_id=None,
        rule_execution_id=None,
        strategy_id=None,
        confidence_evaluation_id=None,
        published_at=None,
    )


@pytest.fixture
def accepted_aggregate(recommendation_id, symbol, direction, confidence_score) -> RecommendationAggregate:
    return RecommendationAggregate(
        id=recommendation_id,
        symbol=symbol,
        direction=direction,
        confidence_score=confidence_score,
        status=RecommendationStatus.ACCEPTED,
        analysis_event_id=None,
        rule_execution_id=None,
        strategy_id=None,
        confidence_evaluation_id=None,
        published_at=None,
    )


@pytest.fixture
def rejected_aggregate(recommendation_id, symbol, direction, confidence_score) -> RecommendationAggregate:
    return RecommendationAggregate(
        id=recommendation_id,
        symbol=symbol,
        direction=direction,
        confidence_score=confidence_score,
        status=RecommendationStatus.REJECTED,
        analysis_event_id=None,
        rule_execution_id=None,
        strategy_id=None,
        confidence_evaluation_id=None,
        published_at=None,
    )


@pytest.fixture
def expired_aggregate(recommendation_id, symbol, direction, confidence_score) -> RecommendationAggregate:
    return RecommendationAggregate(
        id=recommendation_id,
        symbol=symbol,
        direction=direction,
        confidence_score=confidence_score,
        status=RecommendationStatus.EXPIRED,
        analysis_event_id=None,
        rule_execution_id=None,
        strategy_id=None,
        confidence_evaluation_id=None,
        published_at=None,
    )
