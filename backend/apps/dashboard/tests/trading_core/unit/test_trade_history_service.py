from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from apps.dashboard.application.trading_core.services.trade_history_service import (
    TradeHistoryService,
)


class TestTradeHistoryService:
    def test_list_returns_dtos(self) -> None:
        account_id = uuid4()
        mock_repo = MagicMock()

        mock_trade = MagicMock()
        mock_trade.trade_id = uuid4()
        mock_trade.account_id = account_id
        mock_trade.symbol = "RELIANCE"
        mock_trade.side = "LONG"
        mock_trade.entry_price = Decimal("2400.00")
        mock_trade.exit_price = Decimal("2600.00")
        mock_trade.quantity = Decimal("100")
        mock_trade.realized_pnl = Decimal("20000.00")
        mock_trade.realized_pnl_pct = Decimal("8.3333")
        mock_trade.opened_at = None
        mock_trade.closed_at = None
        mock_trade.holding_period_seconds = 86400

        mock_repo.list_all.return_value = [mock_trade]

        service = TradeHistoryService(repository=mock_repo)
        dtos = service.list(account_id)

        assert len(dtos) == 1
        assert dtos[0].symbol == "RELIANCE"
        assert dtos[0].realized_pnl == Decimal("20000.00")
        assert dtos[0].holding_period_seconds == 86400

    def test_list_with_filters(self) -> None:
        account_id = uuid4()
        mock_repo = MagicMock()
        mock_repo.filter_all.return_value = []

        service = TradeHistoryService(repository=mock_repo)
        dtos = service.list(account_id, {"symbol": "RELIANCE"})

        assert len(dtos) == 0
        mock_repo.filter_all.assert_called_once_with(account_id, symbol="RELIANCE")
