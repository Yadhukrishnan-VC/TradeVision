"""Backtest Celery task tests (eager mode)."""

from __future__ import annotations

import uuid

import pytest

from apps.backtesting.infrastructure.tasks import run_backtest

pytestmark = pytest.mark.django_db


def test_task_missing_run(settings) -> None:
    settings.CELERY_TASK_ALWAYS_EAGER = True
    result = run_backtest.delay(str(uuid.uuid4()))
    assert result.get()["status"] == "MISSING"


def test_task_completes_empty_run(backtest_run, settings) -> None:
    settings.CELERY_TASK_ALWAYS_EAGER = True
    result = run_backtest.delay(str(backtest_run.id))
    assert result.get()["status"] == "COMPLETED"
    assert result.get()["bars_processed"] == "0"
    backtest_run.refresh_from_db()
    assert backtest_run.status == "COMPLETED"


def test_task_requires_eager_mode(backtest_run, settings) -> None:
    settings.CELERY_TASK_ALWAYS_EAGER = False
    # Call the task body directly: `.delay()` would reach for a broker router
    # which is not configured in the test env.
    result = run_backtest.run(str(backtest_run.id))
    assert result["status"] == "FAILED"


def test_task_has_expected_metadata() -> None:
    assert run_backtest.name == "tradevision.backtesting.run_backtest"
    assert run_backtest.queue == "analytics"
