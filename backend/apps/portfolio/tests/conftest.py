from __future__ import annotations

import pytest


@pytest.fixture
def account(db, user):
    """A default (primary) account owned by the conftest ``user``.

    Creating the ``Account`` also creates its zero-balance
    ``AccountCapitalState`` via the ``account_capital_created`` signal
    (ADR-028 §19).
    """
    from apps.accounts.infrastructure.models import Account

    return Account.objects.create(
        name="Primary",
        owner=user,
        is_default=True,
    )


@pytest.fixture
def secondary_account(db, user):
    """A non-default account (used to prove single-account resolution)."""
    from apps.accounts.infrastructure.models import Account

    return Account.objects.create(
        name="Secondary",
        owner=user,
        is_default=False,
    )


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
