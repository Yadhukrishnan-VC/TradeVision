"""Remediation Batch — Issue 3 regression test.

The success-path ``logger.info("prompt_template_loaded", extra={"filename":
...})`` in ``PromptManager._load_templates`` passed a reserved LogRecord
attribute, so the logging call raised ``KeyError`` on every iteration, was
swallowed by the broad ``except Exception``, and was silently reported as
``prompt_template_load_failed`` for ALL event types — while the templates
themselves loaded fine (assignment precedes the log call). Worse, the same
exception aborted the loop iteration *before* ``_ensure_persisted_version``,
so template versioning never persisted.

Note on reproduction: ``logging.Logger.log()`` returns early when the level is
disabled, so the reserved-key ``KeyError`` only fires when INFO is enabled on
the module logger. These tests therefore enable INFO via caplog, otherwise the
old bug is masked by the WARNING default.
"""

from __future__ import annotations

import logging

import pytest

from apps.ai_engine.prompt_manager.service import PromptManager, TEMPLATE_NAMES

pytestmark = pytest.mark.django_db

PROMPT_LOGGER = "apps.ai_engine.prompt_manager.service"


class TestPromptManagerLoadsAllTemplates:
    def test_all_event_types_have_a_loaded_template(self) -> None:
        manager = PromptManager()
        assert set(manager._templates.keys()) == set(TEMPLATE_NAMES)
        assert len(manager._templates) == len(TEMPLATE_NAMES) == 11

    def test_no_prompt_template_load_failed_when_info_logging_enabled(
        self, caplog
    ) -> None:
        with caplog.at_level(logging.INFO, logger=PROMPT_LOGGER):
            manager = PromptManager()
        messages = [r.getMessage() for r in caplog.records]
        assert "prompt_template_load_failed" not in messages
        assert "prompt_template_loaded" in messages
        assert set(manager._templates.keys()) == set(TEMPLATE_NAMES)

    def test_template_versions_persisted_on_success_path(self, caplog, settings) -> None:
        """With the old bug the versioning call was never reached because the
        logging exception aborted the loop iteration and was masked as a load
        failure. Persisting all 11 versions proves the full success path runs."""
        settings.PROMPT_VERSIONING_PERSISTENCE_ENABLED = True
        with caplog.at_level(logging.INFO, logger=PROMPT_LOGGER):
            manager = PromptManager()

        from apps.ai_engine.models import PromptVersion

        persisted = set(
            PromptVersion.objects.filter(
                event_type__in=list(TEMPLATE_NAMES)
            ).values_list("event_type", flat=True)
        )
        assert persisted == set(TEMPLATE_NAMES)
        for event_type in TEMPLATE_NAMES:
            assert manager.get_version(event_type) != "unknown"