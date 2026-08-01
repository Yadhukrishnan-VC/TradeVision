from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from apps.pattern_engine.infrastructure.accuracy_lookup import (
    get_historical_recommendation_accuracy,
)


def _patched_objects(created_ids: list, statuses: list) -> MagicMock:
    """Stub ``MemoryEntry.objects`` so the two queries return distinct results.

    The first ``filter(...)`` call (RecommendationCreated) returns ``created_ids``;
    the second (RecommendationStatusChanged) returns ``statuses``.
    """
    mock_mgr = MagicMock()

    def _filter(*args, **kwargs):
        qs = MagicMock()
        event_type = kwargs.get("event_type", "")
        if event_type == "recommendations.RecommendationCreated":
            qs.values_list.return_value = created_ids
        else:
            qs.values_list.return_value = statuses
        return qs

    mock_mgr.filter.side_effect = _filter
    return mock_mgr


class TestHistoricalRecommendationAccuracy:
    def test_returns_none_when_no_created_events(self) -> None:
        with patch(
            "apps.trader_memory.infrastructure.models.MemoryEntry.objects",
            _patched_objects(created_ids=[], statuses=[]),
        ):
            assert get_historical_recommendation_accuracy("RELIANCE") is None

    def test_returns_none_when_no_status_resolutions(self) -> None:
        with patch(
            "apps.trader_memory.infrastructure.models.MemoryEntry.objects",
            _patched_objects(created_ids=["rec-1"], statuses=[]),
        ):
            assert get_historical_recommendation_accuracy("RELIANCE") is None

    def test_computes_win_rate_from_resolutions(self) -> None:
        with patch(
            "apps.trader_memory.infrastructure.models.MemoryEntry.objects",
            _patched_objects(
                created_ids=["rec-1"],
                statuses=["ACCEPTED", "REJECTED", "ACCEPTED"],
            ),
        ):
            result = get_historical_recommendation_accuracy("RELIANCE")
        assert result == Decimal(str(2 / 3))

    def test_uses_case_insensitive_symbol_lookup(self) -> None:
        mock_mgr = MagicMock()

        def _filter(*args, **kwargs):
            qs = MagicMock()
            if kwargs.get("event_type") == "recommendations.RecommendationCreated":
                qs.values_list.return_value = ["rec-1"]
                assert "payload__symbol__iexact" in kwargs
                assert kwargs["payload__symbol__iexact"] == "reliance"
            else:
                qs.values_list.return_value = ["ACCEPTED"]
            return qs

        mock_mgr.filter.side_effect = _filter
        with patch(
            "apps.trader_memory.infrastructure.models.MemoryEntry.objects",
            mock_mgr,
        ):
            get_historical_recommendation_accuracy("reliance")

    def test_lookup_failure_returns_none_and_never_raises(self) -> None:
        with patch(
            "apps.trader_memory.infrastructure.models.MemoryEntry.objects"
        ) as mock_mgr:
            mock_mgr.filter.side_effect = Exception("DB down")
            assert get_historical_recommendation_accuracy("RELIANCE") is None
