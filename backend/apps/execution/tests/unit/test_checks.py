from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.execution.checks import broker_environment_check, capital_readiness_check


class TestBrokerEnvironmentCheck:
    def test_sandbox_default_passes(self, settings) -> None:
        settings.BROKER_ENVIRONMENT = "sandbox"
        settings.ALGO_REGISTRATION_ID = ""
        errors = broker_environment_check()
        assert errors == []

    def test_unknown_environment_fails_e002(self, settings) -> None:
        settings.BROKER_ENVIRONMENT = "moon"
        errors = broker_environment_check()
        assert any(getattr(e, "id", "") == "execution.E002" for e in errors)

    def test_live_without_registration_fails_e003(self, settings) -> None:
        settings.BROKER_ENVIRONMENT = "live"
        settings.ALGO_REGISTRATION_ID = ""
        ids = {getattr(e, "id", "") for e in broker_environment_check()}
        assert "execution.E003" in ids

    def test_live_with_registration_fails_e004_on_bad_format(self, settings) -> None:
        # A registration id with a hyphen fails the anchored format check:
        # E004 requires 8-32 alphanumeric characters.
        settings.BROKER_ENVIRONMENT = "live"
        settings.ALGO_REGISTRATION_ID = "SEBI-ALGO-12345"
        ids = {getattr(e, "id", "") for e in broker_environment_check()}
        assert "execution.E003" not in ids
        assert "execution.E004" in ids

    def test_live_with_registration_resolves_kill_switch_list(self, settings) -> None:
        # E006 reverses the *actual* registered URL name (kill-switch-list),
        # proving the API halt path resolves rather than a lookalike name.
        settings.BROKER_ENVIRONMENT = "live"
        settings.ALGO_REGISTRATION_ID = "SEBI1234567890ABC"
        ids = {getattr(e, "id", "") for e in broker_environment_check()}
        assert "execution.E006" not in ids


class TestCapitalReadinessCheck:
    @pytest.mark.django_db
    def test_empty_watchlist_returns_no_warning(self, settings) -> None:
        settings.MARKET_DATA_POLL_WATCHLIST = []
        assert capital_readiness_check() == []

    @pytest.mark.django_db
    def test_default_capital_clears_all_watchlist_symbols(self, settings) -> None:
        # Default RISK_AVAILABLE_CAPITAL is 1,000,000; mock evidence below it.
        settings.MARKET_DATA_POLL_WATCHLIST = [("NSE", "RELIANCE"), ("NSE", "TCS")]
        with patch(
            "apps.backtesting.application.capital_requirement_service"
            ".min_capital_requirement",
            return_value=Decimal("5000"),
        ):
            assert capital_readiness_check() == []

    @pytest.mark.django_db
    def test_low_capital_warns_w001_for_symbols_that_cannot_size(
        self, settings
    ) -> None:
        settings.RISK_MANAGEMENT = dict(settings.RISK_MANAGEMENT)
        settings.RISK_MANAGEMENT["available_capital"] = Decimal("2000")
        settings.MARKET_DATA_POLL_WATCHLIST = [
            ("NSE", "RELIANCE"),
            ("NSE", "ITC"),
        ]
        evidence = {"RELIANCE": Decimal("11537.74"), "ITC": Decimal("3368.09")}

        def fake_min_capital(symbol, risk_pct, *, worst_case=True):
            return evidence.get(symbol)

        with patch(
            "apps.backtesting.application.capital_requirement_service"
            ".min_capital_requirement",
            side_effect=fake_min_capital,
        ):
            warnings = capital_readiness_check()

        assert len(warnings) == 1
        assert warnings[0].id == "execution.W001"
        assert "RELIANCE" in warnings[0].msg
        assert "ITC" in warnings[0].msg

    def test_skipped_when_no_available_capital_set(self, settings) -> None:
        settings.RISK_MANAGEMENT = {"risk_pct": Decimal("0.01")}
        settings.MARKET_DATA_POLL_WATCHLIST = [("NSE", "RELIANCE")]
        assert capital_readiness_check() == []