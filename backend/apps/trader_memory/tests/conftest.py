from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from apps.eventbus.domain.events import DomainEvent


@pytest.fixture
def recommendation_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def strategy_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def correlation_id() -> uuid.UUID:
    return uuid.uuid4()


def make_recommendation_created_event(
    recommendation_id: str,
    correlation_id: uuid.UUID,
    symbol: str = "RELIANCE",
    direction: str = "BUY",
) -> DomainEvent:
    return DomainEvent.create(
        event_type="recommendations.RecommendationCreated",
        payload={
            "recommendation_id": recommendation_id,
            "symbol": symbol,
            "direction": direction,
            "confidence_score": "0.85",
            "status": "DRAFT",
            "strategy_id": None,
        },
        correlation_id=correlation_id,
    )


def make_recommendation_status_changed_event(
    recommendation_id: str,
    correlation_id: uuid.UUID,
    from_status: str = "DRAFT",
    to_status: str = "PUBLISHED",
    reason: str = "auto-publish",
) -> DomainEvent:
    return DomainEvent.create(
        event_type="recommendations.RecommendationStatusChanged",
        payload={
            "recommendation_id": recommendation_id,
            "from_status": from_status,
            "to_status": to_status,
            "reason": reason,
            "changed_by": "system",
        },
        correlation_id=correlation_id,
    )


@pytest.fixture
def created_event(correlation_id: uuid.UUID, recommendation_id: str) -> DomainEvent:
    return make_recommendation_created_event(recommendation_id, correlation_id)


@pytest.fixture
def status_changed_event(correlation_id: uuid.UUID, recommendation_id: str) -> DomainEvent:
    return make_recommendation_status_changed_event(recommendation_id, correlation_id)
