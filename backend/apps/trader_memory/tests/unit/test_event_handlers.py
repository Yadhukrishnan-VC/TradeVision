from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.eventbus.infrastructure.fake_event_bus import FakeEventBus
from apps.trader_memory.infrastructure.event_handlers import SUBSCRIBED_EVENTS, register_handlers

pytestmark = pytest.mark.django_db


class TestEventHandlers:
    def test_subscribed_events_contains_expected_keys(self) -> None:
        assert "recommendations.RecommendationCreated" in SUBSCRIBED_EVENTS
        assert "recommendations.RecommendationStatusChanged" in SUBSCRIBED_EVENTS

    def test_subscribed_events_are_lists_of_callables(self) -> None:
        for handlers in SUBSCRIBED_EVENTS.values():
            for handler in handlers:
                assert callable(handler)

    def test_register_handlers_subscribes_to_eventbus(self) -> None:
        bus = FakeEventBus()
        register_handlers(bus)
        assert "recommendations.RecommendationCreated" in bus._handlers
        assert "recommendations.RecommendationStatusChanged" in bus._handlers

    def test_register_handlers_uses_correct_consumer_group(self) -> None:
        bus = FakeEventBus()
        register_handlers(bus)
        for handlers in bus._handlers.values():
            for _handler, consumer_group in handlers:
                assert consumer_group == "trader_memory"
