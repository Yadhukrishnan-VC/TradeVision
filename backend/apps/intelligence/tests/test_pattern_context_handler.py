from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from apps.eventbus.domain.events import DomainEvent
from apps.intelligence.infrastructure.pattern_context_handler import handle_pattern_analysis_completed


class TestPatternAnalysisCompletedHandler:
    def test_handler_attaches_pattern_context_to_cache(self) -> None:
        event = DomainEvent.create(
            event_type="pattern_engine.PatternAnalysisCompleted",
            payload={
                "symbol": "RELIANCE",
                "similar_dates": [
                    {
                        "date_str": "2024-03-17",
                        "similarity_score": "0.85",
                        "outcome_summary": "Price rose 2%",
                    },
                ],
                "top_analogue_summary": "Similar to 2024-03-17: price rose 2%",
            },
            correlation_id=uuid.uuid4(),
        )

        with patch("apps.intelligence.infrastructure.pattern_context_handler.MarketContextCache") as mock_cache_cls:
            mock_cache = MagicMock()
            mock_cache_cls.return_value = mock_cache

            handle_pattern_analysis_completed(event)

            assert mock_cache.attach_pattern_context.called
            call_args = mock_cache.attach_pattern_context.call_args
            assert call_args[0][0] == "RELIANCE"

    def test_handler_skips_missing_symbol(self) -> None:
        event = DomainEvent.create(
            event_type="pattern_engine.PatternAnalysisCompleted",
            payload={},
            correlation_id=uuid.uuid4(),
        )

        with patch("apps.intelligence.infrastructure.pattern_context_handler.MarketContextCache") as mock_cache_cls:
            mock_cache = MagicMock()
            mock_cache_cls.return_value = mock_cache

            handle_pattern_analysis_completed(event)

            assert not mock_cache.attach_pattern_context.called

    def test_handler_skips_malformed_payload(self) -> None:
        event = DomainEvent.create(
            event_type="pattern_engine.PatternAnalysisCompleted",
            payload={
                "symbol": "RELIANCE",
                "similar_dates": "not-a-list",
            },
            correlation_id=uuid.uuid4(),
        )

        with patch("apps.intelligence.infrastructure.pattern_context_handler.MarketContextCache") as mock_cache_cls:
            mock_cache = MagicMock()
            mock_cache_cls.return_value = mock_cache

            handle_pattern_analysis_completed(event)

            assert not mock_cache.attach_pattern_context.called
