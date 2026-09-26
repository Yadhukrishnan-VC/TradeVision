"""ADR-030 §5 boundary — the live-capital gate is *actual verification*.

The unit tests in ``tests/unit/test_checks.py`` cover the check function in
isolation. These tests prove the *startup machinery*: running Django's real
system-check framework (what ``manage.py check`` / ``manage.py runserver``
execute) with ``BROKER_ENVIRONMENT=live``. The gate blocks startup with
``SystemCheckError`` while any real precondition is unmet (E003 registration
required, E004 format, E005 risk caps, E006 kill-switch URL, E007 rollback
doc) and permits startup only when every precondition genuinely passes —
live is unlocked by verification, never by registration alone.
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
        assert "execution.E003" in message

    @override_settings(
        BROKER_ENVIRONMENT="live", ALGO_REGISTRATION_ID="SEBI1234567890ABC"
    )
    def test_manage_py_check_passes_when_all_gate_preconditions_met(self) -> None:
        # The ADR-030 §5 gate is "actual verification", not a hardwired block:
        # with a well-formed registration id (E003/E004 pass), a configured
        # positive risk cap (E005 passes), a resolvable kill-switch URL
        # (E006 passes) and a rollback doc on disk (E007 passes), live startup
        # is permitted. The gate only hard-fails when a precondition is
        # *really* unmet — proven in tests/unit/test_checks.py per check id.
        _run_deploy_check()  # must not raise SystemCheckError

    @override_settings(BROKER_ENVIRONMENT="sandbox")
    def test_sandbox_starts_clean(self) -> None:
        _run_deploy_check()

    @override_settings(BROKER_ENVIRONMENT="moon")
    def test_unknown_environment_fails_startup_e002(self) -> None:
        with pytest.raises(SystemCheckError) as excinfo:
            _run_deploy_check()

        assert "execution.E002" in str(excinfo.value)
