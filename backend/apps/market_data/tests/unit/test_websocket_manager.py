from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from threading import Event
from unittest.mock import MagicMock, patch

import pytest

from apps.market_data.domain.entities import Quote
from apps.market_data.infrastructure.websocket_manager import (
    WebSocketTickManager,
)

_INSTRUMENTS = [1001, 1002]


class TestWebSocketTickManager:
    @pytest.fixture
    def mock_tick_source(self) -> MagicMock:
        source = MagicMock()
        source.is_connected = False
        source.connection_state = "disconnected"
        return source

    @pytest.fixture
    def manager(self, mock_tick_source: MagicMock) -> WebSocketTickManager:
        return WebSocketTickManager(tick_source=mock_tick_source)

    def test_initial_state(self, manager: WebSocketTickManager) -> None:
        assert not manager.is_running
        assert manager.connection_state in ("disconnected", "unknown")

    def test_subscribe(self, manager: WebSocketTickManager, mock_tick_source: MagicMock) -> None:
        manager.subscribe(_INSTRUMENTS)
        mock_tick_source.subscribe.assert_called_once_with(_INSTRUMENTS)

    def test_unsubscribe(self, manager: WebSocketTickManager, mock_tick_source: MagicMock) -> None:
        manager.unsubscribe(_INSTRUMENTS)
        mock_tick_source.unsubscribe.assert_called_once_with(_INSTRUMENTS)

    def test_stop_when_not_running(self, manager: WebSocketTickManager) -> None:
        manager.stop()
        assert not manager.is_running

    @patch("apps.market_data.infrastructure.websocket_manager.get_ist_now")
    @patch("apps.market_data.infrastructure.websocket_manager.get_market_calendar")
    def test_should_pause_outside_market_hours(
        self,
        mock_get_calendar: MagicMock,
        mock_get_ist_now: MagicMock,
        mock_tick_source: MagicMock,
    ) -> None:
        from core.market_calendar import MarketCalendar, MarketSession

        calendar = MarketCalendar()
        mock_get_calendar.return_value = calendar

        # Test with holiday
        mock_get_ist_now.return_value = datetime(2025, 3, 10, 12, 0, tzinfo=timezone.utc)
        mock_get_calendar.return_value = calendar
        mock_get_calendar.return_value.is_trading_day = MagicMock(return_value=True)

    def test_backoff_delay(self, manager: WebSocketTickManager) -> None:
        from apps.market_data.infrastructure.websocket_manager import _RECONNECT_DELAYS, _MAX_BACKOFF_DELAY

        for attempt, expected in enumerate(_RECONNECT_DELAYS):
            assert manager._get_backoff_delay() == _RECONNECT_DELAYS[0]

        manager._reconnect_attempt = 0
        assert manager._get_backoff_delay() == 1

        manager._reconnect_attempt = 3
        delays = [1, 2, 4, 8, 16, 30]
        for i in range(len(delays)):
            manager._reconnect_attempt = i
            expected = _RECONNECT_DELAYS[i] if i < len(_RECONNECT_DELAYS) else _MAX_BACKOFF_DELAY

    def test_graceful_shutdown(self, manager: WebSocketTickManager, mock_tick_source: MagicMock) -> None:
        manager.stop()
        assert not manager.is_running
        mock_tick_source.stop.assert_called_once()
