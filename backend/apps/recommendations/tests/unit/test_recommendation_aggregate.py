from __future__ import annotations

import pytest

from apps.recommendations.domain.entities import RecommendationStatus
from apps.recommendations.domain.exceptions import IllegalTransition


class TestRecommendationAggregate:
    def test_draft_can_be_published(self, draft_aggregate) -> None:
        draft_aggregate.publish()
        assert draft_aggregate.status == RecommendationStatus.PUBLISHED
        assert draft_aggregate.published_at is not None

    def test_published_can_be_accepted(self, published_aggregate) -> None:
        published_aggregate.accept()
        assert published_aggregate.status == RecommendationStatus.ACCEPTED

    def test_published_can_be_rejected(self, published_aggregate) -> None:
        published_aggregate.reject()
        assert published_aggregate.status == RecommendationStatus.REJECTED

    def test_published_can_be_expired(self, published_aggregate) -> None:
        published_aggregate.expire()
        assert published_aggregate.status == RecommendationStatus.EXPIRED

    def test_accepted_cannot_transition(self, accepted_aggregate) -> None:
        accepted_aggregate.accept()
        assert accepted_aggregate.status == RecommendationStatus.ACCEPTED

        with pytest.raises(IllegalTransition, match="Cannot transition from ACCEPTED"):
            accepted_aggregate.publish()

        with pytest.raises(IllegalTransition, match="Cannot transition from ACCEPTED"):
            accepted_aggregate.reject()

        with pytest.raises(IllegalTransition, match="Cannot transition from ACCEPTED"):
            accepted_aggregate.expire()

    def test_rejected_cannot_transition(self, rejected_aggregate) -> None:
        rejected_aggregate.reject()
        assert rejected_aggregate.status == RecommendationStatus.REJECTED

        with pytest.raises(IllegalTransition, match="Cannot transition from REJECTED"):
            rejected_aggregate.publish()

        with pytest.raises(IllegalTransition, match="Cannot transition from REJECTED"):
            rejected_aggregate.accept()

        with pytest.raises(IllegalTransition, match="Cannot transition from REJECTED"):
            rejected_aggregate.expire()

    def test_expired_cannot_transition(self, expired_aggregate) -> None:
        expired_aggregate.expire()
        assert expired_aggregate.status == RecommendationStatus.EXPIRED

        with pytest.raises(IllegalTransition, match="Cannot transition from EXPIRED"):
            expired_aggregate.publish()

        with pytest.raises(IllegalTransition, match="Cannot transition from EXPIRED"):
            expired_aggregate.accept()

        with pytest.raises(IllegalTransition, match="Cannot transition from EXPIRED"):
            expired_aggregate.reject()

    def test_draft_cannot_accept(self, draft_aggregate) -> None:
        with pytest.raises(IllegalTransition, match="Cannot transition from DRAFT to ACCEPTED"):
            draft_aggregate.accept()

    def test_draft_cannot_reject(self, draft_aggregate) -> None:
        with pytest.raises(IllegalTransition, match="Cannot transition from DRAFT to REJECTED"):
            draft_aggregate.reject()

    def test_draft_cannot_expire(self, draft_aggregate) -> None:
        with pytest.raises(IllegalTransition, match="Cannot transition from DRAFT to EXPIRED"):
            draft_aggregate.expire()
