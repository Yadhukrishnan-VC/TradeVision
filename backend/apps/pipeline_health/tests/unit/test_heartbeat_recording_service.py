from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.pipeline_health.application.heartbeat_recording_service import (
    HeartbeatRecordingService,
)
from apps.pipeline_health.domain.exceptions import (
    MissingSymbolError,
    UnsupportedEventTypeError,
)


class _RecordingRepo:
    """In-memory fake capturing the upsert arguments (no DB)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def upsert(self, **kwargs) -> None:
        self.calls.append(kwargs)

    def latest_for_stage(self, stage):  # noqa: ARG002 - protocol stub
        return None


def _event(event_type: str, symbol: str | None = None, token: int | None = None):
    payload: dict[str, object] = {}
    if symbol is not None:
        payload["symbol"] = symbol
    if token is not None:
        payload["instrument_token"] = token
    return DomainEvent.create(
        event_type=event_type,
        payload=payload,
        correlation_id=uuid.uuid4(),
    )


@pytest.fixture
def repo() -> _RecordingRepo:
    return _RecordingRepo()


@pytest.fixture
def service(repo: _RecordingRepo) -> HeartbeatRecordingService:
    return HeartbeatRecordingService(repository=repo)


class TestEventMapping:
    def test_candles_persisted_maps_to_market_data_with_symbol(self, service, repo):
        service.record(_event("marketdata.CandlesPersisted", token=2885))

        assert len(repo.calls) == 1
        call = repo.calls[0]
        assert call["stage"].value == "MARKET_DATA"
        assert call["symbol_scope"] == "token:2885"
        assert call["last_event_id"]

    def test_candles_persisted_with_resolver_uses_symbol(self, repo):
        service = HeartbeatRecordingService(
            repository=repo,
            symbol_resolver=lambda token: "RELIANCE",
        )

        service.record(_event("marketdata.CandlesPersisted", token=2885))

        assert repo.calls[0]["symbol_scope"] == "RELIANCE"

    def test_candles_persisted_unresolvable_token_falls_back(self, service, repo):
        service.record(_event("marketdata.CandlesPersisted", token=999999))

        assert repo.calls[0]["symbol_scope"] == "token:999999"

    def test_technical_analysis_maps_symbol(self, service, repo):
        service.record(
            _event("technical_analysis.TechnicalAnalysisCompleted", symbol="RELIANCE")
        )

        assert repo.calls[0]["stage"].value == "TECHNICAL_ANALYSIS"
        assert repo.calls[0]["symbol_scope"] == "RELIANCE"

    def test_packet_built_maps_symbol(self, service, repo):
        service.record(_event("intelligence.PacketBuilt", symbol="TCS"))

        assert repo.calls[0]["stage"].value == "INTELLIGENCE"
        assert repo.calls[0]["symbol_scope"] == "TCS"

    def test_rule_fired_maps_symbol(self, service, repo):
        service.record(_event("rule_engine.RuleFired", symbol="SBIN"))

        assert repo.calls[0]["stage"].value == "RULE_ENGINE"
        assert repo.calls[0]["symbol_scope"] == "SBIN"

    def test_order_filled_maps_global_scope(self, service, repo):
        service.record(_event("orders.OrderFilled"))

        assert repo.calls[0]["stage"].value == "EXECUTION"
        assert repo.calls[0]["symbol_scope"] == "GLOBAL"

    def test_symbol_is_upper_cased(self, service, repo):
        service.record(_event("intelligence.PacketBuilt", symbol="tcs"))

        assert repo.calls[0]["symbol_scope"] == "TCS"

    def test_unknown_event_type_raises(self, service):
        with pytest.raises(UnsupportedEventTypeError):
            service.record(_event("unknown.Something"))

    def test_missing_symbol_raises(self, service):
        with pytest.raises(MissingSymbolError):
            service.record(_event("intelligence.PacketBuilt"))


class TestTimestampSemantics:
    def test_records_event_occurred_at_not_wall_clock(self, service, repo):
        occurred = datetime(2026, 8, 11, 9, 30, 0, tzinfo=timezone.utc)
        event = DomainEvent(
            event_id=uuid.uuid4(),
            event_type="intelligence.PacketBuilt",
            occurred_at=occurred,
            payload={"symbol": "RELIANCE"},
            version=1,
            correlation_id=uuid.uuid4(),
        )

        service.record(event)

        assert repo.calls[0]["last_event_at"] == occurred

    def test_records_event_and_correlation_ids(self, service, repo):
        event = _event("rule_engine.RuleFired", symbol="RELIANCE")

        service.record(event)

        assert repo.calls[0]["last_event_id"] == event.event_id
        assert repo.calls[0]["last_correlation_id"] == event.correlation_id
