from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _use_fake_event_bus() -> None:
    """Route published events to the in-memory FakeEventBus."""
    from django.conf import settings

    from apps.eventbus.infrastructure.event_bus_factory import (
        get_event_bus,
        reset_event_bus,
    )

    settings.EVENT_BUS_IMPLEMENTATION = "fake"
    reset_event_bus()
    yield get_event_bus()
    reset_event_bus()


@pytest.fixture
def register_consumers():
    """Register the pipeline-health consumers on the active bus."""

    def _register(bus=None):
        from apps.pipeline_health.infrastructure.event_consumers import (
            register_consumers,
        )

        register_consumers(bus)

    return _register


@pytest.fixture
def instrument(db):
    """A tradeable instrument (NSE:RELIANCE) for token->symbol resolution."""
    from apps.market_data.infrastructure.models import Instrument

    return Instrument.objects.create(
        instrument_token=2885,
        exchange="NSE",
        tradingsymbol="RELIANCE",
        name="Reliance Industries",
        segment="EQUITY",
        is_active=True,
    )
