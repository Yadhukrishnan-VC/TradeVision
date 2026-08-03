from __future__ import annotations

from django.conf import settings

POLL_TASK = "apps.eventbus.infrastructure.tasks.poll_event_streams"
REPLAY_TASK = "apps.eventbus.infrastructure.tasks.replay_unpublished_events"


def test_beat_schedule_contains_eventbus_poll_task() -> None:
    assert POLL_TASK in {
        entry["task"] for entry in settings.CELERY_BEAT_SCHEDULE.values()
    }
    entry = next(
        e for e in settings.CELERY_BEAT_SCHEDULE.values() if e["task"] == POLL_TASK
    )
    assert entry["options"]["queue"] == "maintenance"
    assert entry["schedule"] == 2.0


def test_beat_schedule_contains_replay_unpublished_task() -> None:
    assert REPLAY_TASK in {
        entry["task"] for entry in settings.CELERY_BEAT_SCHEDULE.values()
    }
    entry = next(
        e for e in settings.CELERY_BEAT_SCHEDULE.values() if e["task"] == REPLAY_TASK
    )
    assert entry["options"]["queue"] == "maintenance"
    assert entry["schedule"] == 30.0