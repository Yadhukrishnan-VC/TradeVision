from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest

from apps.common.domain.base_entity import BaseEntity


class _ConcreteEntity(BaseEntity):
    def __init__(self, id: uuid.UUID | None = None) -> None:
        super().__init__(id=id)
        self.name: str = ""


class TestBaseEntity:
    def test_auto_generates_uuid(self) -> None:
        entity = _ConcreteEntity()
        assert isinstance(entity.id, uuid.UUID)

    def test_sets_created_at_on_init(self) -> None:
        entity = _ConcreteEntity()
        assert isinstance(entity.created_at, datetime)

    def test_sets_updated_at_on_init(self) -> None:
        entity = _ConcreteEntity()
        assert isinstance(entity.updated_at, datetime)

    def test_accepts_explicit_id(self) -> None:
        explicit_id = uuid.uuid4()
        entity = _ConcreteEntity(id=explicit_id)
        assert entity.id == explicit_id

    def test_register_event_appends_to_pending(self) -> None:
        entity = _ConcreteEntity()
        assert len(entity._pending_events) == 0
        event = _FakeDomainEvent()
        entity.register_event(event)
        assert len(entity._pending_events) == 1

    def test_pull_events_drains_pending_list(self) -> None:
        entity = _ConcreteEntity()
        event = _FakeDomainEvent()
        entity.register_event(event)
        events = entity.pull_events()
        assert len(events) == 1
        assert events[0] is event
        assert len(entity.pull_events()) == 0

    def test_pull_events_returns_empty_list_when_no_events(self) -> None:
        entity = _ConcreteEntity()
        assert entity.pull_events() == []

    def test_equality_by_id(self) -> None:
        explicit_id = uuid.uuid4()
        a = _ConcreteEntity(id=explicit_id)
        b = _ConcreteEntity(id=explicit_id)
        assert a == b

    def test_inequality_different_ids(self) -> None:
        a = _ConcreteEntity()
        b = _ConcreteEntity()
        assert a != b

    def test_hash_by_id(self) -> None:
        explicit_id = uuid.uuid4()
        a = _ConcreteEntity(id=explicit_id)
        b = _ConcreteEntity(id=explicit_id)
        assert hash(a) == hash(b)

    def test_register_event_accepts_any_type(self) -> None:
        entity = _ConcreteEntity()
        entity.register_event("not an event")  # type: ignore[arg-type]
        assert len(entity.pull_events()) == 1


class _FakeDomainEvent:
    """Minimal stand-in for DomainEvent for testing purposes."""
    pass
