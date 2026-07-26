from __future__ import annotations

"""Event handlers for the accounts app.

This module follows the convention expected by EventBusService:
it exposes a ``register_handlers(event_bus)`` function that
subscribes this app's handlers to the events they consume.
"""

from typing import Any

from apps.eventbus.application.ports import EventBus


def register_handlers(event_bus: EventBus) -> None:
    """Register accounts event handlers with the event bus.

    Currently, accounts does not consume any domain events.
    This function exists for convention and will be populated
    when cross-app event subscriptions are defined in later batches.

    Args:
        event_bus: The configured EventBus instance.
    """
    pass
