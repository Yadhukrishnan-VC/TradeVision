from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.recommendations.infrastructure.event_handlers import (
    SUBSCRIBED_EVENTS,
    _handle_rule_fired,
    register_handlers,
)


class TestEventHandlers:
    def test_subscribed_events_contains_rule_fired(self) -> None:
        assert "rule_engine.RuleFired" in SUBSCRIBED_EVENTS

    def test_rule_fired_has_one_handler(self) -> None:
        handlers = SUBSCRIBED_EVENTS["rule_engine.RuleFired"]
        assert len(handlers) == 1
        assert handlers[0] is _handle_rule_fired

    @patch("apps.recommendations.infrastructure.event_handlers.create_recommendation")
    def test_handle_rule_fired_dispatches_task(self, mock_create_recommendation) -> None:
        cid = uuid.uuid4()
        event = DomainEvent.create(
            event_type="rule_engine.RuleFired",
            payload={
                "symbol": "RELIANCE",
                "rule_id": "rule-123",
                "analysis_event_id": "evt-456",
                "trigger_data": {"change_pct": "2.5"},
            },
            correlation_id=cid,
        )

        _handle_rule_fired(event)

        mock_create_recommendation.delay.assert_called_once_with(
            symbol="RELIANCE",
            rule_id="rule-123",
            analysis_event_id="evt-456",
            trigger_data={"change_pct": "2.5"},
            correlation_id=str(event.correlation_id),
        )

    @patch("apps.recommendations.infrastructure.event_handlers.create_recommendation")
    def test_handle_rule_fired_without_optional_fields(self, mock_create_recommendation) -> None:
        cid = uuid.uuid4()
        event = DomainEvent.create(
            event_type="rule_engine.RuleFired",
            payload={
                "symbol": "TCS",
                "rule_id": "rule-456",
            },
            correlation_id=cid,
        )

        _handle_rule_fired(event)

        mock_create_recommendation.delay.assert_called_once_with(
            symbol="TCS",
            rule_id="rule-456",
            analysis_event_id=None,
            trigger_data={},
            correlation_id=str(event.correlation_id),
        )

    def test_register_handlers_subscribes_to_event_bus(self) -> None:
        bus = MagicMock()

        register_handlers(bus)

        bus.subscribe.assert_called_once_with(
            event_type="rule_engine.RuleFired",
            handler=_handle_rule_fired,
            consumer_group="recommendations",
        )

    def test_register_handlers_with_mocked_subscribe(self) -> None:
        bus = MagicMock()

        register_handlers(bus)

        bus.subscribe.assert_called_once()
        call_args = bus.subscribe.call_args
        assert call_args[1]["event_type"] == "rule_engine.RuleFired"
        assert call_args[1]["consumer_group"] == "recommendations"
