"""
Tests for core.constants — enum value uniqueness and string values.
"""

from core.constants import (
    AIProviderName,
    MarketStatus,
    NotificationType,
    QueueName,
    RecommendationDirection,
    RecommendationOutcome,
    RecommendationTimeHorizon,
    RiskLevel,
    TaskName,
)


class TestEnumUniqueness:
    """Every enum must have unique values within its class."""

    def _check_unique(self, cls: type) -> None:
        values = [member.value for member in cls]
        assert len(values) == len(set(values)), f"{cls.__name__} has duplicate values"

    def test_market_status_unique(self) -> None:
        self._check_unique(MarketStatus)

    def test_recommendation_direction_unique(self) -> None:
        self._check_unique(RecommendationDirection)

    def test_recommendation_time_horizon_unique(self) -> None:
        self._check_unique(RecommendationTimeHorizon)

    def test_recommendation_outcome_unique(self) -> None:
        self._check_unique(RecommendationOutcome)

    def test_risk_level_unique(self) -> None:
        self._check_unique(RiskLevel)

    def test_notification_type_unique(self) -> None:
        self._check_unique(NotificationType)

    def test_ai_provider_name_unique(self) -> None:
        self._check_unique(AIProviderName)

    def test_task_name_unique(self) -> None:
        self._check_unique(TaskName)

    def test_queue_name_unique(self) -> None:
        self._check_unique(QueueName)


class TestStringValues:
    """Enums used as string values must be str-typed."""

    def test_market_status_is_str(self) -> None:
        assert isinstance(MarketStatus.OPEN, str)

    def test_recommendation_direction_is_str(self) -> None:
        assert isinstance(RecommendationDirection.BUY, str)

    def test_risk_level_is_str(self) -> None:
        assert isinstance(RiskLevel.LOW, str)

    def test_task_name_is_str(self) -> None:
        assert isinstance(TaskName.INGEST_MARKET_DATA, str)

    def test_queue_name_is_str(self) -> None:
        assert isinstance(QueueName.AI, str)
