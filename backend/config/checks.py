"""
Environment ↔ database separation checks.

Registered under the ``config`` tag via ``apps.common.apps.CommonConfig.ready()``.

Prevents the class of mistake that already happened once in this project: a
process booted with live/production settings pointed at a test database (or dev
settings pointed at a non-dev database), silently reading/writing the wrong
data. These checks fail startup loudly instead of letting the misconfiguration
through.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.core import checks

# pytest / Django test-runner settings modules: their databases are managed by
# the runner (auto-prefixed ``test_...``) and never point at a live DB, so the
# separation rules below do not apply.
_TEST_HARNESS_SETTINGS = frozenset({"config.settings.test", "config.settings.testing"})

# DB names that signal a development/test database. Dev/test settings MUST point
# at a database whose name carries one of these markers as a name token
# (boundary-delimited), e.g. tradevision_test, tradevision_dev_db, test_xxx.
_DEV_DB_MARKERS = ("test", "dev")

# Settings module name fragments that signal a live (production/staging) env.
_LIVE_SETTINGS_MARKERS = ("prod", "staging")

# Settings module name fragments that signal a development/test env.
_DEV_SETTINGS_MARKERS = ("dev", "test")


def _name_has_marker(db_name: str, marker: str) -> bool:
    """True when ``marker`` appears in ``db_name`` as a delimited name token.

    Boundary-aware so "dev" inside "tradevision_db" does not count, while
    "tradevision_test", "tradevision_dev_db", and "test_tradevision_db" do.
    """
    return bool(
        re.search(rf"(^|[_\-.]|\\d){marker}([_\-.]|\\d|$)", db_name, re.IGNORECASE)
    )


@checks.register("config")
def environment_database_separation_check(
    app_configs=None, **kwargs
) -> list[checks.Error]:
    """Fail startup when the environment and database name disagree.

    - Live settings (``prod``/``staging`` in DJANGO_SETTINGS_MODULE) pointed at
      a database whose name contains ``test`` → ``config.E001``.
    - Dev/test settings pointed at a database whose name contains neither
      ``test`` nor ``dev`` → ``config.E002``.

    The pytest harness (``config.settings.test`` / ``config.settings.testing``)
    is exempt: the runner creates its own ``test_<name>`` database.
    """
    errors: list[checks.Error] = []

    settings_module = getattr(settings, "SETTINGS_MODULE", "") or ""
    if settings_module in _TEST_HARNESS_SETTINGS:
        return errors

    db_name = settings.DATABASES["default"].get("NAME") or ""
    module = settings_module.lower()
    db = db_name.lower()

    is_live = any(marker in module for marker in _LIVE_SETTINGS_MARKERS)
    is_dev = any(marker in module for marker in _DEV_SETTINGS_MARKERS)

    if is_live and _name_has_marker(db, "test"):
        errors.append(
            checks.Error(
                f"Live settings ({settings_module}) are pointed at database "
                f"{db_name!r}, which looks like a test database.",
                hint=(
                    "Set POSTGRES_DB to the live database (name must not "
                    "contain 'test') when DJANGO_SETTINGS_MODULE is a "
                    "production/staging module."
                ),
                id="config.E001",
            )
        )

    if is_dev and not any(_name_has_marker(db, marker) for marker in _DEV_DB_MARKERS):
        errors.append(
            checks.Error(
                f"Development settings ({settings_module}) are pointed at "
                f"database {db_name!r}, whose name contains neither 'test' "
                f"nor 'dev'.",
                hint=(
                    "Set POSTGRES_DB to a database whose name contains "
                    "'test' or 'dev' (e.g. tradevision_test, tradevision_dev_db)."
                ),
                id="config.E002",
            )
        )

    return errors
