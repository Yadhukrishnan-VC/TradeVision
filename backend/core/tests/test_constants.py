"""
Tests for core/constants.py.

Verifies that:
    - All enums are str enums (values are plain strings)
    - Values within each enum are unique across members
    - Key expected members and values are present
    - TaskName values follow the ``tradevision.`` prefix convention
    - QueueName contains all eight required queues
"""

import pytest

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


# ---------------------------------------------------------------------------
# MarketStatus
# ---------------------------------------------------------------------------


class TestMarketStatus:
    """Tests for the MarketStatus enum."""

    def test_all_values_are_strings(self) -> None:
        """Every MarketStatus value must be a plain string."""
        for member in MarketStatus:
            assert isinstance(member.value, str), (
                f"MarketStatus.{member.name}.value is not a str: {member.value!r}"
            )

    def test_values_are_unique(self) -> None:
        """No two MarketStatus members may share the same value."""
        values = [m.value for m in MarketStatus]
        assert len(values) == len(set(values)), (
            f"Duplicate values in MarketStatus: {values}"
        )

    def test_expected_members_exist(self) -> None:
        """Core market states must be present."""
        assert MarketStatus.OPEN.value == "open"
        assert MarketStatus.CLOSED.value == "closed"
        assert MarketStatus.HOLIDAY.value == "holiday"
        assert MarketStatus.PRE_OPEN.value == "pre_open"
        assert MarketStatus.POST_CLOSE.value == "post_close"


# ---------------------------------------------------------------------------
# RecommendationDirection
# ---------------------------------------------------------------------------


class TestRecommendationDirection:
    """Tests for the RecommendationDirection enum."""

    def test_all_values_are_strings(self) -> None:
        for member in RecommendationDirection:
            assert isinstance(member.value, str)

    def test_values_are_unique(self) -> None:
        values = [m.value for m in RecommendationDirection]
        assert len(values) == len(set(values))

    def test_exactly_four_directions(self) -> None:
        """The AI can only emit BUY, SELL, WATCH, or AVOID."""
        expected = {"BUY", "SELL", "WATCH", "AVOID"}
        actual = {m.value for m in RecommendationDirection}
        assert actual == expected, f"Direction mismatch: {actual} != {expected}"


# ---------------------------------------------------------------------------
# RecommendationTimeHorizon
# ---------------------------------------------------------------------------


class TestRecommendationTimeHorizon:
    """Tests for the RecommendationTimeHorizon enum."""

    def test_all_values_are_strings(self) -> None:
        for member in RecommendationTimeHorizon:
            assert isinstance(member.value, str)

    def test_values_are_unique(self) -> None:
        values = [m.value for m in RecommendationTimeHorizon]
        assert len(values) == len(set(values))

    def test_intraday_exists(self) -> None:
        assert RecommendationTimeHorizon.INTRADAY.value == "INTRADAY"

    def test_long_exists(self) -> None:
        assert RecommendationTimeHorizon.LONG.value == "LONG"


# ---------------------------------------------------------------------------
# RecommendationOutcome
# ---------------------------------------------------------------------------


class TestRecommendationOutcome:
    """Tests for the RecommendationOutcome enum."""

    def test_all_values_are_strings(self) -> None:
        for member in RecommendationOutcome:
            assert isinstance(member.value, str)

    def test_values_are_unique(self) -> None:
        values = [m.value for m in RecommendationOutcome]
        assert len(values) == len(set(values))

    def test_pending_is_initial_state(self) -> None:
        """New recommendations start in PENDING state."""
        assert RecommendationOutcome.PENDING.value == "PENDING"

    def test_all_terminal_states_exist(self) -> None:
        terminal = {"CORRECT", "INCORRECT", "PARTIAL", "INCONCLUSIVE"}
        actual = {m.value for m in RecommendationOutcome}
        assert terminal.issubset(actual)


# ---------------------------------------------------------------------------
# RiskLevel
# ---------------------------------------------------------------------------


class TestRiskLevel:
    """Tests for the RiskLevel enum."""

    def test_all_values_are_strings(self) -> None:
        for member in RiskLevel:
            assert isinstance(member.value, str)

    def test_values_are_unique(self) -> None:
        values = [m.value for m in RiskLevel]
        assert len(values) == len(set(values))

    def test_four_levels_exist(self) -> None:
        expected = {"LOW", "MEDIUM", "HIGH", "VERY_HIGH"}
        actual = {m.value for m in RiskLevel}
        assert actual == expected


# ---------------------------------------------------------------------------
# NotificationType
# ---------------------------------------------------------------------------


class TestNotificationType:
    """Tests for the NotificationType enum."""

    def test_all_values_are_strings(self) -> None:
        for member in NotificationType:
            assert isinstance(member.value, str)

    def test_values_are_unique(self) -> None:
        values = [m.value for m in NotificationType]
        assert len(values) == len(set(values))

    def test_recommendation_type_exists(self) -> None:
        assert NotificationType.RECOMMENDATION.value == "recommendation"

    def test_operational_types_exist(self) -> None:
        """Admin-only operational alert types must be present."""
        assert NotificationType.FEED_DEGRADED.value == "feed_degraded"
        assert NotificationType.AI_BUDGET_WARNING.value == "ai_budget_warning"
        assert NotificationType.STALE_DATA.value == "stale_data"


# ---------------------------------------------------------------------------
# AIProviderName
# ---------------------------------------------------------------------------


class TestAIProviderName:
    """Tests for the AIProviderName enum."""

    def test_all_values_are_strings(self) -> None:
        for member in AIProviderName:
            assert isinstance(member.value, str)

    def test_values_are_unique(self) -> None:
        values = [m.value for m in AIProviderName]
        assert len(values) == len(set(values))

    def test_gemini_is_default_provider(self) -> None:
        """Gemini is the Phase 0 active provider."""
        assert AIProviderName.GEMINI.value == "gemini"

    def test_all_four_providers_exist(self) -> None:
        expected = {"gemini", "openai", "claude", "ollama"}
        actual = {m.value for m in AIProviderName}
        assert actual == expected, f"Provider mismatch: {actual} != {expected}"

    def test_values_are_lowercase(self) -> None:
        """Provider names must be lowercase to match settings comparison."""
        for member in AIProviderName:
            assert member.value == member.value.lower(), (
                f"AIProviderName.{member.name} value '{member.value}' must be lowercase"
            )


# ---------------------------------------------------------------------------
# QueueName
# ---------------------------------------------------------------------------


class TestQueueName:
    """Tests for the QueueName enum."""

    def test_all_values_are_strings(self) -> None:
        for member in QueueName:
            assert isinstance(member.value, str)

    def test_values_are_unique(self) -> None:
        values = [m.value for m in QueueName]
        assert len(values) == len(set(values))

    def test_all_eight_queues_exist(self) -> None:
        """All eight named queues declared in the architecture must be present."""
        required = {
            "market_data",
            "processing",
            "intelligence",
            "rule_engine",
            "ai",
            "notifications",
            "analytics",
            "default",
        }
        actual = {m.value for m in QueueName}
        missing = required - actual
        assert not missing, f"Missing queues: {missing}"

    def test_default_queue_exists(self) -> None:
        assert QueueName.DEFAULT.value == "default"

    def test_ai_queue_exists(self) -> None:
        assert QueueName.AI.value == "ai"


# ---------------------------------------------------------------------------
# TaskName
# ---------------------------------------------------------------------------


class TestTaskName:
    """Tests for the TaskName enum."""

    def test_all_values_are_strings(self) -> None:
        for member in TaskName:
            assert isinstance(member.value, str)

    def test_values_are_unique(self) -> None:
        values = [m.value for m in TaskName]
        assert len(values) == len(set(values))

    def test_all_values_have_tradevision_prefix(self) -> None:
        """All task names must start with ``tradevision.`` for namespacing."""
        for member in TaskName:
            assert member.value.startswith("tradevision."), (
                f"TaskName.{member.name} = '{member.value}' must start with 'tradevision.'"
            )

    def test_ai_call_task_exists(self) -> None:
        assert TaskName.CALL_AI_PROVIDER.value == "tradevision.ai_engine.call"

    def test_ingestion_task_exists(self) -> None:
        assert TaskName.INGEST_MARKET_DATA.value == "tradevision.market_data.ingest"
