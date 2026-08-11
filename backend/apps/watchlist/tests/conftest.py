from __future__ import annotations

import pytest


@pytest.fixture
def account(db, user):
    """A default (primary) account owned by the conftest ``user``."""
    from apps.accounts.infrastructure.models import Account

    return Account.objects.create(
        name="Primary",
        owner=user,
        is_default=True,
    )


@pytest.fixture
def secondary_account(db, user):
    """A non-default account owned by the conftest ``user``."""
    from apps.accounts.infrastructure.models import Account

    return Account.objects.create(
        name="Secondary",
        owner=user,
        is_default=False,
    )


@pytest.fixture
def other_user(db):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.create_user(
        username="other-owner",
        password="SecurePass123!",
    )


@pytest.fixture
def foreign_account(db, other_user):
    """An account owned by a different user (ownership-rejection tests)."""
    from apps.accounts.infrastructure.models import Account

    return Account.objects.create(
        name="Foreign",
        owner=other_user,
        is_default=False,
    )


@pytest.fixture
def instrument(db):
    """A tradeable instrument (NSE:RELIANCE)."""
    from apps.market_data.infrastructure.models import Instrument

    return Instrument.objects.create(
        instrument_token=2885,
        exchange="NSE",
        tradingsymbol="RELIANCE",
        name="Reliance Industries",
        segment="EQUITY",
        is_active=True,
    )


@pytest.fixture
def instruments(db):
    """Three ordered instruments for list/reorder tests."""
    from apps.market_data.infrastructure.models import Instrument

    rows = [
        (2885, "NSE", "RELIANCE", "Reliance Industries"),
        (22, "NSE", "SBIN", "State Bank of India"),
        (1329, "NSE", "TCS", "Tata Consultancy Services"),
    ]
    return [
        Instrument.objects.create(
            instrument_token=token,
            exchange=exchange,
            tradingsymbol=tradingsymbol,
            name=name,
            segment="EQUITY",
            is_active=True,
        )
        for token, exchange, tradingsymbol, name in rows
    ]
