from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from apps.eventbus.domain.events import DomainEvent
from core.events.event_types import (
    BreadthContext,
    CircuitStatus,
    DataQuality,
    IntelligencePacket,
    NewsContext,
    PriceContext,
    TechnicalContext,
)


class TestTradingSignalBridge:
    def test_price_context_optional_fields_default_to_none(self) -> None:
        ctx = PriceContext(
            current_price=Decimal("0"),
            open_price=Decimal("0"),
            high=Decimal("0"),
            low=Decimal("0"),
            prev_close=None,
            change_pct=None,
            volume=0,
            avg_volume_20d=0,
            circuit_status=CircuitStatus.NORMAL,
        )
        assert ctx.prev_close is None
        assert ctx.change_pct is None

    def test_intelligence_packet_with_optional_none_fields(self) -> None:
        packet = IntelligencePacket(
            symbol="TEST",
            timestamp=datetime.now(timezone.utc),
            freshness_validated=True,
            price_context=PriceContext(
                current_price=Decimal("100.00"),
                open_price=Decimal("99.00"),
                high=Decimal("101.00"),
                low=Decimal("98.50"),
                prev_close=None,
                change_pct=None,
                volume=100000,
                avg_volume_20d=50000,
                circuit_status=CircuitStatus.NORMAL,
            ),
            technical_context=TechnicalContext(),
            breadth_context=BreadthContext(
                sector_index_change_pct=Decimal("0.00"),
                sector_advance_decline=Decimal("0.00"),
                nifty_change_pct=Decimal("0.00"),
                sensex_change_pct=Decimal("0.00"),
            ),
            news_context=NewsContext(),
            data_quality=DataQuality(),
        )
        assert packet.price_context.prev_close is None
        assert packet.price_context.change_pct is None

    @override_settings(MARKET_CONTEXT_SCORING_ENABLED=True)
    def test_handle_signal_created_publishes_market_context(self) -> None:
        cid = uuid.uuid4()
        event = DomainEvent.create(
            event_type="signals.SignalCreated",
            payload={
                "symbol": "RELIANCE",
                "signal_id": str(uuid.uuid4()),
                "direction": "BUY",
                "confidence_hint": 0.85,
            },
            correlation_id=cid,
        )

        with (
            patch("apps.intelligence.infrastructure.trading_signal_bridge.TASnapshotRepository") as mock_repo_cls,
            patch("apps.intelligence.infrastructure.trading_signal_bridge.PineOutput.objects.filter") as mock_pine_filter,
            patch("apps.intelligence.infrastructure.trading_signal_bridge.get_event_bus") as mock_get_bus,
            patch("apps.intelligence.infrastructure.trading_signal_bridge.MarketContextCache") as mock_cache_cls,
        ):
            mock_repo = MagicMock()
            mock_snapshot = MagicMock()
            mock_snapshot.raw_payload = {
                "close": "2500.00",
                "open": "2480.00",
                "high": "2520.00",
                "low": "2470.00",
                "volume": "2000000",
                "prev_close": "2480.00",
                "change_pct": "0.81",
            }
            mock_repo.find_by_symbol.return_value = [mock_snapshot]
            mock_repo_cls.return_value = mock_repo

            mock_pine_qs = MagicMock()
            mock_pine_qs.order_by.return_value.first.return_value = None
            mock_pine_filter.return_value = mock_pine_qs

            mock_bus = MagicMock()
            mock_get_bus.return_value = mock_bus

            mock_cache = MagicMock()
            mock_cache_cls.return_value = mock_cache

            from apps.intelligence.infrastructure.trading_signal_bridge import handle_signal_created
            result = handle_signal_created(event)

            assert result is not None
            assert result.symbol == "RELIANCE"

            assert mock_bus.publish.called
            published_event = mock_bus.publish.call_args[0][0]
            assert published_event.event_type == "intelligence.MarketContextBuilt"
            assert published_event.correlation_id == cid
            assert published_event.causation_id == event.event_id
            assert published_event.payload["symbol"] == "RELIANCE"
            assert "bullishness_score" in published_event.payload
            assert "market_regime" in published_event.payload

            assert mock_cache.set.called
            assert mock_cache.set.call_args[0][0] == "RELIANCE"

    @override_settings(MARKET_CONTEXT_SCORING_ENABLED=True)
    def test_handle_signal_created_publish_failure_does_not_raise(self) -> None:
        event = DomainEvent.create(
            event_type="signals.SignalCreated",
            payload={
                "symbol": "RELIANCE",
                "signal_id": str(uuid.uuid4()),
                "direction": "BUY",
                "confidence_hint": 0.85,
            },
            correlation_id=uuid.uuid4(),
        )

        with (
            patch("apps.intelligence.infrastructure.trading_signal_bridge.TASnapshotRepository") as mock_repo_cls,
            patch("apps.intelligence.infrastructure.trading_signal_bridge.PineOutput.objects.filter") as mock_pine_filter,
            patch("apps.intelligence.infrastructure.trading_signal_bridge.get_event_bus") as mock_get_bus,
            patch("apps.intelligence.infrastructure.trading_signal_bridge.MarketContextCache") as mock_cache_cls,
        ):
            mock_repo = MagicMock()
            mock_snapshot = MagicMock()
            mock_snapshot.raw_payload = {"close": "2500.00"}
            mock_repo.find_by_symbol.return_value = [mock_snapshot]
            mock_repo_cls.return_value = mock_repo

            mock_pine_qs = MagicMock()
            mock_pine_qs.order_by.return_value.first.return_value = None
            mock_pine_filter.return_value = mock_pine_qs

            mock_bus = MagicMock()
            mock_bus.publish.side_effect = Exception("Bus failure")
            mock_get_bus.return_value = mock_bus

            mock_cache = MagicMock()
            mock_cache_cls.return_value = mock_cache

            from apps.intelligence.infrastructure.trading_signal_bridge import handle_signal_created
            result = handle_signal_created(event)

            assert result is not None
            assert result.symbol == "RELIANCE"

    @override_settings(MARKET_CONTEXT_SCORING_ENABLED=True)
    def test_handle_signal_created_correlation_chain_preserved(self) -> None:
        cid = uuid.uuid4()
        event = DomainEvent.create(
            event_type="signals.SignalCreated",
            payload={
                "symbol": "RELIANCE",
                "signal_id": str(uuid.uuid4()),
                "direction": "WATCH",
                "confidence_hint": 0.5,
            },
            correlation_id=cid,
        )

        with (
            patch("apps.intelligence.infrastructure.trading_signal_bridge.TASnapshotRepository") as mock_repo_cls,
            patch("apps.intelligence.infrastructure.trading_signal_bridge.PineOutput.objects.filter") as mock_pine_filter,
            patch("apps.intelligence.infrastructure.trading_signal_bridge.get_event_bus") as mock_get_bus,
            patch("apps.intelligence.infrastructure.trading_signal_bridge.MarketContextCache") as mock_cache_cls,
        ):
            mock_repo = MagicMock()
            mock_snapshot = MagicMock()
            mock_snapshot.raw_payload = {"close": "2500.00"}
            mock_repo.find_by_symbol.return_value = [mock_snapshot]
            mock_repo_cls.return_value = mock_repo

            mock_pine_qs = MagicMock()
            mock_pine_qs.order_by.return_value.first.return_value = None
            mock_pine_filter.return_value = mock_pine_qs

            mock_bus = MagicMock()
            mock_get_bus.return_value = mock_bus

            mock_cache = MagicMock()
            mock_cache_cls.return_value = mock_cache

            from apps.intelligence.infrastructure.trading_signal_bridge import handle_signal_created
            handle_signal_created(event)

            published_event = mock_bus.publish.call_args[0][0]
            assert published_event.correlation_id == cid
            assert published_event.causation_id == event.event_id
