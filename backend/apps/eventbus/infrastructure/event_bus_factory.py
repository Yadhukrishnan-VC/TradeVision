from __future__ import annotations

from django.conf import settings

from apps.eventbus.application.ports import EventBus


_event_bus_instance: EventBus | None = None


def get_event_bus() -> EventBus:
    """Return a configured EventBus singleton based on settings.

    The implementation is selected by ``settings.EVENT_BUS_IMPLEMENTATION``:
    - ``"redis"`` → :class:`RedisStreamsEventBus`
    - ``"fake"`` → :class:`FakeEventBus`

    Returns:
        An EventBus instance (singleton per process).
    """
    global _event_bus_instance

    if _event_bus_instance is not None:
        return _event_bus_instance

    implementation = getattr(settings, "EVENT_BUS_IMPLEMENTATION", "redis")

    if implementation == "fake":
        from apps.eventbus.infrastructure.fake_event_bus import FakeEventBus
        _event_bus_instance = FakeEventBus()
    else:
        from apps.eventbus.infrastructure.redis_event_bus import RedisStreamsEventBus
        _event_bus_instance = RedisStreamsEventBus()

    return _event_bus_instance


def reset_event_bus() -> None:
    """Reset the singleton (primarily for testing)."""
    global _event_bus_instance
    _event_bus_instance = None
