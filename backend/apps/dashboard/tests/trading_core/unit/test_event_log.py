from __future__ import annotations

import uuid

import pytest

from apps.dashboard.infrastructure.common.event_log import EventLog

pytestmark = pytest.mark.django_db


class TestEventLog:
    def test_has_been_applied_returns_false_for_new_event(self) -> None:
        event_id = uuid.uuid4()
        assert EventLog.objects.has_been_applied(event_id, "test_projector") is False

    def test_has_been_applied_returns_true_after_marking(self) -> None:
        event_id = uuid.uuid4()
        EventLog.objects.mark_applied(event_id, "test_projector")
        assert EventLog.objects.has_been_applied(event_id, "test_projector") is True

    def test_mark_applied_creates_record(self) -> None:
        event_id = uuid.uuid4()
        record = EventLog.objects.mark_applied(event_id, "test_projector")
        assert record.event_id == event_id
        assert record.projector == "test_projector"
        assert record.applied_at is not None

    def test_unique_constraint_prevents_duplicate(self) -> None:
        event_id = uuid.uuid4()
        EventLog.objects.mark_applied(event_id, "test_projector")
        with pytest.raises(Exception):
            EventLog.objects.mark_applied(event_id, "test_projector")

    def test_different_projectors_can_log_same_event(self) -> None:
        event_id = uuid.uuid4()
        EventLog.objects.mark_applied(event_id, "projector_a")
        record = EventLog.objects.mark_applied(event_id, "projector_b")
        assert record.event_id == event_id
        assert record.projector == "projector_b"
