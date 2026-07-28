from __future__ import annotations

from unittest.mock import MagicMock

from apps.ai_engine.infrastructure.event_handlers import (
    SUBSCRIBED_EVENTS,
    _handle_rule_fired,
    register_handlers,
)


class TestAIEngineEventHandlers:
    def test_subscribed_events_contains_rule_fired(self) -> None:
        assert "rule_engine.RuleFired" in SUBSCRIBED_EVENTS

    def test_rule_fired_has_one_handler(self) -> None:
        handlers = SUBSCRIBED_EVENTS["rule_engine.RuleFired"]
        assert len(handlers) == 1
        assert handlers[0] is _handle_rule_fired

    def test_register_handlers_subscribes_to_event_bus(self) -> None:
        bus = MagicMock()
        register_handlers(bus)
        bus.subscribe.assert_called_once_with(
            event_type="rule_engine.RuleFired",
            handler=_handle_rule_fired,
            consumer_group="ai_engine",
        )
