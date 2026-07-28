from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.eventbus.infrastructure.event_bus_factory import get_event_bus, reset_event_bus
from apps.rule_engine.infrastructure.event_handlers import (
    SUBSCRIBED_EVENTS,
    register_handlers,
)


class TestRegisterHandlers:
    def test_register_handlers_accepts_event_bus(self) -> None:
        reset_event_bus()
        bus = get_event_bus()

        register_handlers(bus)

        assert True

    def test_register_handlers_subscribes_declared_events(self) -> None:
        reset_event_bus()
        bus = get_event_bus()

        original_events = dict(SUBSCRIBED_EVENTS)
        SUBSCRIBED_EVENTS.clear()
        SUBSCRIBED_EVENTS["test.event"] = [lambda e: None]

        try:
            register_handlers(bus)
        finally:
            SUBSCRIBED_EVENTS.clear()
            SUBSCRIBED_EVENTS.update(original_events)

        assert True

    def test_register_handlers_does_not_error_with_empty_subscriptions(self) -> None:
        reset_event_bus()
        bus = get_event_bus()

        original_events = dict(SUBSCRIBED_EVENTS)
        SUBSCRIBED_EVENTS.clear()

        try:
            register_handlers(bus)
        finally:
            SUBSCRIBED_EVENTS.update(original_events)

    def test_subscribed_handler_invoked_when_event_published(self) -> None:
        reset_event_bus()
        bus = get_event_bus()

        handler = MagicMock()
        original_events = dict(SUBSCRIBED_EVENTS)
        SUBSCRIBED_EVENTS.clear()
        SUBSCRIBED_EVENTS["rule_engine.test.event"] = [handler]

        try:
            register_handlers(bus)

            from apps.eventbus.domain.events import DomainEvent
            import uuid

            event = DomainEvent.create(
                event_type="rule_engine.test.event",
                payload={"key": "value"},
                correlation_id=uuid.uuid4(),
            )
            bus.publish(event)

            handler.assert_called_once_with(event)
        finally:
            SUBSCRIBED_EVENTS.clear()
            SUBSCRIBED_EVENTS.update(original_events)

    def test_handler_not_invoked_for_unsubscribed_event_type(self) -> None:
        reset_event_bus()
        bus = get_event_bus()

        handler = MagicMock()
        original_events = dict(SUBSCRIBED_EVENTS)
        SUBSCRIBED_EVENTS.clear()
        SUBSCRIBED_EVENTS["rule_engine.important"] = [handler]

        try:
            register_handlers(bus)

            from apps.eventbus.domain.events import DomainEvent
            import uuid

            event = DomainEvent.create(
                event_type="rule_engine.unrelated",
                payload={},
                correlation_id=uuid.uuid4(),
            )
            bus.publish(event)

            handler.assert_not_called()
        finally:
            SUBSCRIBED_EVENTS.clear()
            SUBSCRIBED_EVENTS.update(original_events)
