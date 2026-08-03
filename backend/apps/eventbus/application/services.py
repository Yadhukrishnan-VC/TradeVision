from __future__ import annotations

import importlib
import logging
import weakref

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

    # Event bus instances that have already completed a full registration
    # pass. ``AppConfig.ready()`` is invoked once per installed app and each
    # of those call sites re-invokes ``register_all_handlers()``; the guard
    # below makes every call after the first a no-op so each handler ends up
    # subscribed exactly once. State is tracked per bus instance (weak
    # references, keyed by object identity), not globally for the process, so
    # ``reset_event_bus()`` swapping in a fresh instance yields a fresh pass.
    _registered_buses: weakref.WeakSet[EventBus] = weakref.WeakSet()

    @staticmethod
    def reset_registration_state() -> None:
        """Forget every bus that already completed a registration pass.

        Test-only hook that mirrors ``reset_event_bus()``: lets a test swap
        in a fresh bus instance and force a clean re-registration pass.
        """
        EventBusService._registered_buses.clear()

    @staticmethod
    def register_all_handlers() -> None:
        """Discover and register event handlers from every installed app.

        For each installed app that has a module at
        ``<app_label>.infrastructure.event_handlers`` with a callable
        ``register_handlers(event_bus)``, invoke it.

        Idempotent: the registration pass is applied at most once per
        EventBus instance, no matter how many times this method is called.

        Raises:
            ImportError: If an app's event_handlers module is found
                but cannot be imported. Fails loudly at startup.
        """
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
        event_bus = get_event_bus()

        if event_bus in EventBusService._registered_buses:
            return

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

        EventBusService._registered_buses.add(event_bus)
