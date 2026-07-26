from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus, reset_event_bus


@pytest.fixture(autouse=True)
def _reset_event_bus() -> Generator[None, None, None]:
    reset_event_bus()
    yield
    reset_event_bus()


@pytest.fixture
def sample_event() -> DomainEvent:
    return DomainEvent.create(
        event_type="test.SomethingHappened",
        payload={"key": "value", "count": 42},
        correlation_id=uuid.uuid4(),
    )
