"""PORTFOLIO-DAILY-CAPITAL — tests for the daily capital reset task."""

from __future__ import annotations

import pytest
from decimal import Decimal

from apps.portfolio.application.capital_service import CapitalService
from apps.portfolio.tasks import reset_daily_capital

pytestmark = pytest.mark.django_db


class TestResetDailyCapital:
    def test_noop_when_disabled(self, settings, account) -> None:
        settings.PORTFOLIO_DAILY_CAPITAL = Decimal("0")

        outcome = reset_daily_capital()

        assert outcome == {"applied": False, "reason": "disabled"}
        state = CapitalService().get_state(account.id)
        assert state.cash == Decimal(0)

    def test_applies_daily_capital_to_primary_account(self, settings, account) -> None:
        settings.PORTFOLIO_DAILY_CAPITAL = Decimal("2000")
        CapitalService().deposit(account.id, Decimal("100"))  # leftover from prior day

        outcome = reset_daily_capital()

        assert outcome["applied"] is True
        assert Decimal(outcome["cash"]) == Decimal("2000")
        state = CapitalService().get_state(account.id)
        assert state.cash == Decimal("2000")

    def test_explicit_account_id_overrides_primary(self, settings, account, secondary_account) -> None:
        settings.PORTFOLIO_DAILY_CAPITAL = Decimal("2000")
        CapitalService().deposit(secondary_account.id, Decimal("500"))

        outcome = reset_daily_capital(account_id=str(secondary_account.id))

        assert outcome["applied"] is True
        assert outcome["account_id"] == str(secondary_account.id)
        assert CapitalService().get_state(secondary_account.id).cash == Decimal("2000")
        assert CapitalService().get_state(secondary_account.id).cash == Decimal("2000")
        assert CapitalService().get_state(account.id).cash == Decimal(0)

    def test_noop_when_no_primary_account(self, settings, user, secondary_account) -> None:
        settings.PORTFOLIO_DAILY_CAPITAL = Decimal("2000")

        outcome = reset_daily_capital()

        assert outcome == {"applied": False, "reason": "no-primary-account"}