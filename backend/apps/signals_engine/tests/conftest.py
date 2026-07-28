from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus, reset_event_bus


@pytest.fixture(autouse=True)
def reset_bus() -> Generator[None, None, None]:
    reset_event_bus()
    yield
    bus = get_event_bus()
    if hasattr(bus, "clear"):
        bus.clear()
    reset_event_bus()


@pytest.fixture
def raw_alert_payload() -> dict[str, Any]:
    return {
        "raw_payload": {
            "ticker": "RELIANCE",
            "close": 2850.50,
            "time": "2026-07-28T10:00:00Z",
            "volume": 5000000,
            "direction": "BUY",
            "timeframe": "1h",
            "confidence_hint": 0.75,
            "indicator_snapshot": {
                "rsi_14": 62.5,
                "macd": 12.30,
                "ema_20": 2830.00,
            },
            "alert_id": "tv_alert_001",
        },
        "source": "tradingview",
        "received_at": "2026-07-28T10:00:00Z",
        "signature_valid": True,
    }


@pytest.fixture
def raw_alert_event(raw_alert_payload: dict[str, Any]) -> DomainEvent:
    import uuid
    return DomainEvent.create(
        event_type="ingestion.RawAlertReceived",
        payload=raw_alert_payload,
        correlation_id=uuid.uuid4(),
    )
