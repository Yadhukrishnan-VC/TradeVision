"""Environment ↔ database separation check (config.E001 / config.E002).

Regression tests for ``config.checks.environment_database_separation_check`` —
the startup guard that fails loudly when live settings point at a test database
or dev settings point at a database whose name carries no test/dev marker.
"""

from __future__ import annotations

import pytest

from config import checks


def _run(monkeypatch, settings_module: str, db_name: str):
    from django.conf import settings

    monkeypatch.setattr(settings, "SETTINGS_MODULE", settings_module)
    monkeypatch.setattr(
        settings,
        "DATABASES",
        {"default": {"NAME": db_name}},
    )
    return checks.environment_database_separation_check()


class TestLiveEnvironment:
    def test_production_settings_pointed_at_test_db_fails(self, monkeypatch):
        errors = _run(monkeypatch, "config.settings.production", "tradevision_test")
        assert {e.id for e in errors} == {"config.E001"}

    def test_staging_settings_pointed_at_test_db_fails(self, monkeypatch):
        errors = _run(monkeypatch, "config.settings.staging", "test_tradevision_db")
        assert {e.id for e in errors} == {"config.E001"}

    def test_production_settings_pointed_at_live_db_passes(self, monkeypatch):
        errors = _run(monkeypatch, "config.settings.production", "tradevision_live")
        assert errors == []


class TestDevelopmentEnvironment:
    def test_dev_settings_pointed_at_non_dev_db_fails(self, monkeypatch):
        errors = _run(monkeypatch, "config.settings.development", "tradevision_db")
        assert {e.id for e in errors} == {"config.E002"}

    def test_dev_settings_pointed_at_test_db_passes(self, monkeypatch):
        errors = _run(monkeypatch, "config.settings.development", "tradevision_test")
        assert errors == []

    def test_dev_settings_pointed_at_dev_db_passes(self, monkeypatch):
        errors = _run(monkeypatch, "config.settings.dev", "tradevision_dev_db")
        assert errors == []

    def test_digit_boundary_counts_as_marker(self, monkeypatch):
        # Regression: the marker regex must match a digit boundary ("test2"),
        # not just "_" / "." / end-of-string delimiters.
        errors = _run(monkeypatch, "config.settings.development", "tradevision_fresh_test2")
        assert errors == []

    def test_devdb_is_not_matched_inside_tradevision(self, monkeypatch):
        # "dev" is a substring of "tradevision" — must not count as a marker.
        errors = _run(monkeypatch, "config.settings.development", "tradevision_db")
        assert "config.E002" in {e.id for e in errors}


class TestTestHarnessExempt:
    @pytest.mark.parametrize(
        "module", ["config.settings.testing", "config.settings.test"]
    )
    def test_test_harness_settings_are_exempt(self, monkeypatch, module):
        errors = _run(monkeypatch, module, "tradevision_db")
        assert errors == []
