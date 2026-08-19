"""Future data leakage integrity.

Attacks attempted:
- Seed a bar AFTER ``range_end`` and check it neither gets processed nor
  generates orders (a strategy must never trade on data outside the declared
  sample).
- Seed a bar just outside the range boundaries (``range_start - 1min`` and
  ``range_end + 1min``) and confirm the window is INCLUSIVE on both ends and
  excludes anything outside it (RESEARCH-INTEGRITY-3).

Findings:
- ``find_in_range`` is inclusive on both ends: the boundary bars at exactly
  ``range_start`` and ``range_end`` are processed, and one minute either side
  is not. No future bar reaches the engine (no-defect finding).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from tests.research_integrity.conftest import RUN_END, RUN_START

pytestmark = pytest.mark.django_db


def test_bars_outside_run_range_are_not_processed(replay):
    """Only the inclusive boundary bars are processed; one minute outside is
    excluded."""
    bars = [
        (RUN_START - timedelta(minutes=1), "100.00", "103.00"),  # before range
        (RUN_START, "100.00", "103.00"),  # inclusive start
        (RUN_END, "100.00", "103.00"),  # inclusive end
        (RUN_END + timedelta(minutes=1), "100.00", "103.00"),  # after range
    ]
    _run, result, _bus = replay(seed_bars=bars)

    assert result["status"] == "COMPLETED"
    assert result["bars_processed"] == "2"


def test_future_bar_after_range_end_generates_no_order(replay):
    """A strong-signal bar after the range end must never be processed."""
    future = RUN_END + timedelta(days=30)
    _run, result, _bus = replay(
        seed_bars=[
            (future, "50.00", "200.00"),  # extreme move, but in the future
        ]
    )

    from apps.execution.infrastructure.models import Order

    assert result["status"] == "COMPLETED"
    assert result["bars_processed"] == "0"
    assert Order.objects.filter(account_id=_run.account_id).count() == 0