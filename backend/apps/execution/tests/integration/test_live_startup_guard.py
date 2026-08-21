"""ADR-030 §5 boundary — ``BROKER_ENVIRONMENT=live`` must fail startup.

The unit tests in ``tests/unit/test_checks.py`` cover the check function in
isolation. These tests prove the *startup machinery*: running Django's real
system-check framework (what ``manage.py check`` / ``manage.py runserver``
execute) with ``BROKER_ENVIRONMENT=live`` raises ``SystemCheckError``
carrying ``execution.E001``. The Phase-2 gate requires removing E001 by
design, never by accident — this test fails loudly if the guard weakens.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.checks.registry import registry as check_registry
from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.test import override_settings


def _run_deploy_check() -> None:
    """Run the same system-check pass startup performs, output captured."""
    call_command("check", stdout=StringIO(), stderr=StringIO())


class TestLiveEnvironmentFailsStartup:
    def test_broker_environment_check_is_registered(self) -> None:
        # Guard against the registration itself being dropped: if apps.ready()
        # stops importing the decorated checks module, real startup would run
        # no broker-environment validation at all.
        names = [getattr(fn, "__name__", "") for fn in check_registry.registered_checks]
        assert "broker_environment_check" in names

    @override_settings(BROKER_ENVIRONMENT="live", ALGO_REGISTRATION_ID="")
    def test_manage_py_check_fails_on_live_without_registration(self) -> None:
        with pytest.raises(SystemCheckError) as excinfo:
            _run_deploy_check()

        message = str(excinfo.value)
        assert "execution.E001" in message
        assert "execution.E003" in message

    @override_settings(
        BROKER_ENVIRONMENT="live", ALGO_REGISTRATION_ID="SEBI-ALGO-12345"
    )
    def test_manage_py_check_fails_on_live_even_with_registration(self) -> None:
        # The Phase 2 explicit unlock does not exist: a recorded registration
        # id satisfies E003 but E001 (ADR-030 Phase-1 sandbox-only guard)
        # still blocks startup. This is the assertion that matters for the
        # gate — live stays unreachable until E001 is removed *by design*.
        with pytest.raises(SystemCheckError) as excinfo:
            _run_deploy_check()

        message = str(excinfo.value)
        assert "execution.E001" in message
        assert "execution.E003" not in message

    @override_settings(BROKER_ENVIRONMENT="sandbox")
    def test_sandbox_starts_clean(self) -> None:
        _run_deploy_check()

    @override_settings(BROKER_ENVIRONMENT="moon")
    def test_unknown_environment_fails_startup_e002(self) -> None:
        with pytest.raises(SystemCheckError) as excinfo:
            _run_deploy_check()

        assert "execution.E002" in str(excinfo.value)
