from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _fake_event_bus(settings) -> None:
    """In-memory event bus.

    The wildcard-subscription tests drive ``bus.publish(...)`` and expect the
    ``audit_log`` consumer (subscribed to ``*``) to run inline. With the
    default Redis bus, ``publish`` only mirrors to the stream, so no
    ``AuditLogEntry`` is ever written.
    """
    from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus

    settings.EVENT_BUS_IMPLEMENTATION = "fake"
    reset_event_bus()
    yield
    reset_event_bus()
