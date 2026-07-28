from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from apps.eventbus.domain.events import DomainEvent
from apps.intelligence.infrastructure.ta_completed_handler import handle_ta_completed


class TestHandleTACompleted:
    def test_missing_symbol_logs_warning(self) -> None:
        event = DomainEvent.create(
            event_type="technical_analysis.TechnicalAnalysisCompleted",
            payload={},
            correlation_id=uuid.uuid4(),
        )
        handle_ta_completed(event)

    def test_publishes_packet_enriched_for_valid_payload(self) -> None:
        cid = uuid.uuid4()
        event = DomainEvent.create(
            event_type="technical_analysis.TechnicalAnalysisCompleted",
            payload={
                "symbol": "RELIANCE",
                "snapshot_id": "snap-123",
                "exchange": "NSE",
                "timeframe": "1D",
                "snapshot_timestamp": "2026-07-28T10:00:00+00:00",
                "indicators": {"rsi_14": 62.5, "macd": 1.23},
                "price": {"close": "3124.50", "high": "3145.00"},
                "pine_id": "test_script",
                "pine_version": "5",
            },
            correlation_id=cid,
        )

        with patch("apps.intelligence.infrastructure.ta_completed_handler.get_event_bus") as mock_get_bus:
            mock_bus = MagicMock()
            mock_get_bus.return_value = mock_bus
            with patch("apps.intelligence.infrastructure.ta_completed_handler.IntelligenceService") as mock_intel:
                mock_service = MagicMock()
                mock_intel.return_value = mock_service

                handle_ta_completed(event)

                assert mock_bus.publish.called
                published_event = mock_bus.publish.call_args[0][0]
                assert published_event.event_type == "intelligence.PacketEnriched"
                assert published_event.payload["symbol"] == "RELIANCE"
                assert published_event.correlation_id == cid
                assert published_event.causation_id == event.event_id

                assert mock_service.build_packet.called

    def test_handles_malformed_snapshot_timestamp_gracefully(self) -> None:
        event = DomainEvent.create(
            event_type="technical_analysis.TechnicalAnalysisCompleted",
            payload={
                "symbol": "TCS",
                "snapshot_id": "snap-456",
                "exchange": "NSE",
                "snapshot_timestamp": "invalid-date",
            },
            correlation_id=uuid.uuid4(),
        )

        with patch("apps.intelligence.infrastructure.ta_completed_handler.get_event_bus") as mock_get_bus:
            mock_get_bus.return_value = MagicMock()
            with patch("apps.intelligence.infrastructure.ta_completed_handler.IntelligenceService") as mock_intel:
                mock_intel.return_value = MagicMock()

                handle_ta_completed(event)
