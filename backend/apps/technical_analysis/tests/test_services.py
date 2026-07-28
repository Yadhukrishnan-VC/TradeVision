from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from apps.technical_analysis.application.services import (
    TechnicalAnalysisIngestionService,
)
from apps.technical_analysis.domain.exceptions import (
    InvalidFieldValueError,
    MissingRequiredFieldError,
    SnapshotPersistenceError,
)


class TestValidate:
    def test_valid_payload_passes(self) -> None:
        service = TechnicalAnalysisIngestionService(
            repository=MagicMock(), event_bus=MagicMock()
        )
        payload = {"ticker": "RELIANCE", "close": 2850.50}
        result = service.validate(payload)
        assert result["ticker"] == "RELIANCE"
        assert result["close"] == 2850.50

    def test_missing_required_field_raises(self) -> None:
        service = TechnicalAnalysisIngestionService(
            repository=MagicMock(), event_bus=MagicMock()
        )
        with pytest.raises(MissingRequiredFieldError):
            service.validate({"ticker": "RELIANCE"})

    def test_empty_ticker_raises(self) -> None:
        service = TechnicalAnalysisIngestionService(
            repository=MagicMock(), event_bus=MagicMock()
        )
        with pytest.raises(MissingRequiredFieldError):
            service.validate({"close": 100.0, "ticker": ""})

    def test_non_dict_payload_raises(self) -> None:
        service = TechnicalAnalysisIngestionService(
            repository=MagicMock(), event_bus=MagicMock()
        )
        with pytest.raises(Exception):
            service.validate("not_a_dict")

    def test_symbol_field_maps_to_ticker(self) -> None:
        service = TechnicalAnalysisIngestionService(
            repository=MagicMock(), event_bus=MagicMock()
        )
        result = service.validate({"symbol": "TCS", "close": 150.0})
        assert result["ticker"] == "TCS"

    def test_price_field_maps_to_close(self) -> None:
        service = TechnicalAnalysisIngestionService(
            repository=MagicMock(), event_bus=MagicMock()
        )
        result = service.validate({"ticker": "TCS", "price": 150.0})
        assert result["close"] == 150.0

    def test_case_insensitive_keys(self) -> None:
        service = TechnicalAnalysisIngestionService(
            repository=MagicMock(), event_bus=MagicMock()
        )
        result = service.validate({"TICKER": "INFY", "CLOSE": 1700.0})
        assert result["ticker"] == "INFY"
        assert result["close"] == 1700.0


class TestNormalise:
    def test_known_fields_are_mapped(self) -> None:
        service = TechnicalAnalysisIngestionService(
            repository=MagicMock(), event_bus=MagicMock()
        )
        payload = {
            "ticker": "RELIANCE",
            "close": 2850.50,
            "high": 2860.00,
            "low": 2840.00,
            "volume": 1000000,
        }
        result = service.normalise(payload)
        assert result["ticker"] == "RELIANCE"
        assert result["close"] == 2850.50
        assert result["high"] == 2860.00

    def test_time_field_converts_to_datetime(self) -> None:
        service = TechnicalAnalysisIngestionService(
            repository=MagicMock(), event_bus=MagicMock()
        )
        payload = {"ticker": "RELIANCE", "close": 2850.50, "time": 1699000000000}
        result = service.normalise(payload)
        assert "snapshot_timestamp" in result
        assert isinstance(result["snapshot_timestamp"], datetime)
        assert result["snapshot_timestamp"].tzinfo is not None

    def test_unknown_fields_become_indicators(self) -> None:
        service = TechnicalAnalysisIngestionService(
            repository=MagicMock(), event_bus=MagicMock()
        )
        payload = {
            "ticker": "RELIANCE",
            "close": 2850.50,
            "rsi": 62.5,
            "sma_20": 2830.00,
        }
        result = service.normalise(payload)
        assert "indicators" in result
        assert result["indicators"]["rsi"] == 62.5
        assert result["indicators"]["sma_20"] == 2830.00

    def test_pine_metadata_preserved(self) -> None:
        service = TechnicalAnalysisIngestionService(
            repository=MagicMock(), event_bus=MagicMock()
        )
        payload = {
            "ticker": "RELIANCE",
            "close": 2850.50,
            "pine_id": "my_script",
            "pine_version": "5",
            "pine_timestamp": 1699000000000,
        }
        result = service.normalise(payload)
        assert result["pine_id"] == "my_script"
        assert result["pine_version"] == "5"
        assert result["pine_timestamp"] == 1699000000000


class TestIngest:
    def test_happy_path(self) -> None:
        repo = MagicMock()
        repo.save.side_effect = lambda entity: entity
        bus = MagicMock()
        service = TechnicalAnalysisIngestionService(
            repository=repo, event_bus=bus
        )
        payload = {
            "ticker": "RELIANCE",
            "close": 2850.50,
            "exchange": "NSE",
            "timeframe": "15min",
            "rsi": 62.5,
            "pine_id": "test_script",
            "pine_version": "5",
        }

        snapshot = service.ingest(payload)

        assert snapshot.symbol == "RELIANCE"
        assert snapshot.exchange == "NSE"
        assert snapshot.timeframe == "15min"
        assert snapshot.indicators["rsi"] == 62.5
        assert snapshot.pine_metadata.pine_id == "test_script"
        assert snapshot.pine_metadata.pine_version == "5"

        repo.save.assert_called_once()
        bus.publish.assert_called_once()

    def test_repository_failure_raises(self) -> None:
        repo = MagicMock()
        repo.save.side_effect = Exception("DB error")
        bus = MagicMock()
        service = TechnicalAnalysisIngestionService(
            repository=repo, event_bus=bus
        )

        with pytest.raises(SnapshotPersistenceError):
            service.ingest({"ticker": "HDFC", "close": 1600.0})

        bus.publish.assert_not_called()

    def test_event_published_with_correct_type(self) -> None:
        repo = MagicMock()
        repo.save.side_effect = lambda entity: entity
        bus = MagicMock()
        service = TechnicalAnalysisIngestionService(
            repository=repo, event_bus=bus
        )

        service.ingest({"ticker": "TCS", "close": 3500.0})

        call_args = bus.publish.call_args
        event = call_args[0][0]
        assert event.event_type == "technical_analysis.TechnicalAnalysisCompleted"
        assert event.payload["symbol"] == "TCS"

    def test_correlation_id_preserved(self) -> None:
        repo = MagicMock()
        repo.save.side_effect = lambda entity: entity
        bus = MagicMock()
        service = TechnicalAnalysisIngestionService(
            repository=repo, event_bus=bus
        )
        cid = uuid.uuid4()

        service.ingest(
            {"ticker": "TCS", "close": 3500.0},
            correlation_id=cid,
        )

        call_args = bus.publish.call_args
        event = call_args[0][0]
        assert event.correlation_id == cid

    def test_indicator_keys_in_event(self) -> None:
        repo = MagicMock()
        repo.save.side_effect = lambda entity: entity
        bus = MagicMock()
        service = TechnicalAnalysisIngestionService(
            repository=repo, event_bus=bus
        )

        service.ingest(
            {
                "ticker": "TCS",
                "close": 3500.0,
                "rsi_14": 65.0,
                "macd": 12.5,
                "bb_upper": 3600.0,
            }
        )

        call_args = bus.publish.call_args
        event = call_args[0][0]
        assert sorted(event.payload["indicator_keys"]) == sorted(
            ["rsi_14", "macd", "bb_upper"]
        )
