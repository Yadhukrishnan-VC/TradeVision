from __future__ import annotations

from apps.execution.checks import broker_environment_check


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

    def test_live_without_registration_fails_e001_and_e003(self, settings) -> None:
        settings.BROKER_ENVIRONMENT = "live"
        settings.ALGO_REGISTRATION_ID = ""
        ids = {getattr(e, "id", "") for e in broker_environment_check()}
        assert "execution.E001" in ids
        assert "execution.E003" in ids

    def test_live_with_registration_fails_only_e001(self, settings) -> None:
        settings.BROKER_ENVIRONMENT = "live"
        settings.ALGO_REGISTRATION_ID = "SEBI-ALGO-12345"
        ids = {getattr(e, "id", "") for e in broker_environment_check()}
        assert "execution.E001" in ids
        assert "execution.E003" not in ids