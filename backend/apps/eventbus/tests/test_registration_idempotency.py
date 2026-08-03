from __future__ import annotations

from typing import Any

from django.test import override_settings

from apps.eventbus.application.services import EventBusService
from apps.eventbus.infrastructure.event_bus_factory import (
    get_event_bus,
    reset_event_bus,
)


def _handler_path(handler: Any) -> str:
    return f"{handler.__module__}.{handler.__name__}" if callable(handler) else str(handler)


def _flat_entries(bus: Any) -> list[tuple[str, str]]:
    """Flatten the handler table into (event_type, handler_path, group) tuples."""
    entries: list[tuple[str, str, str]] = []
    for event_type, handler_list in bus.handlers.items():
        for handler, consumer_group in handler_list:
            entries.append((event_type, _handler_path(handler), consumer_group))
    return entries


@override_settings(EVENT_BUS_IMPLEMENTATION="fake")
def test_register_all_handlers_is_idempotent_on_same_instance() -> None:
    """N calls to register_all_handlers() must produce the same table as one call."""
    reset_event_bus()
    EventBusService.reset_registration_state()

    bus = get_event_bus()
    EventBusService.register_all_handlers()
    single_pass = _flat_entries(bus)

    for _ in range(3):
        EventBusService.register_all_handlers()

    repeated_passes = _flat_entries(bus)

    assert single_pass == repeated_passes
    assert len(single_pass) > 0
    # No duplicate (event_type, handler_path, consumer_group) ever appears.
    assert len(single_pass) == len(set(single_pass))


@override_settings(EVENT_BUS_IMPLEMENTATION="fake")
def test_register_all_handlers_fresh_bus_gets_full_registration() -> None:
    """A fresh bus instance (post-reset) still receives a normal full pass."""
    reset_event_bus()
    EventBusService.reset_registration_state()

    get_event_bus()
    EventBusService.register_all_handlers()
    first = _flat_entries(get_event_bus())

    # Swapping to a fresh bus (as tests deliberately do via reset_event_bus)
    # must start from a clean slate rather than being short-circuited by the
    # process-level guard.
    reset_event_bus()
    get_event_bus()
    EventBusService.register_all_handlers()
    second = _flat_entries(get_event_bus())

    assert len(first) > 0
    assert first == second