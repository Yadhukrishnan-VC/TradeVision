from __future__ import annotations

import importlib
import logging
from typing import Any

from django.apps import apps

from apps.eventbus.application.ports import EventBus

logger = logging.getLogger(__name__)


class EventBusService:
    """Orchestrates event bus handler registration across all apps.

    At startup, this service scans every installed Django app for a
    module named ``infrastructure.event_handlers`` and, if it exports
    a ``register_handlers`` function, calls it with the configured
    EventBus instance.
    """

    @staticmethod
    def register_all_handlers() -> None:
        """Discover and register event handlers from every installed app.

        For each installed app that has a module at
        ``<app_label>.infrastructure.event_handlers`` with a callable
        ``register_handlers(event_bus)``, invoke it.

        Raises:
            ImportError: If an app's event_handlers module is found
                but cannot be imported. Fails loudly at startup.
        """
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
        event_bus = get_event_bus()

        for app_config in apps.get_app_configs():
            module_name = f"{app_config.name}.infrastructure.event_handlers"
            try:
                module = importlib.import_module(module_name)
            except ModuleNotFoundError:
                continue

            register_fn = getattr(module, "register_handlers", None)
            if register_fn is None:
                continue

            try:
                register_fn(event_bus)
                logger.info(
                    "Registered event handlers",
                    extra={"app": app_config.label},
                )
            except Exception:
                logger.exception(
                    "Failed to register event handlers",
                    extra={"app": app_config.label},
                )
                raise
