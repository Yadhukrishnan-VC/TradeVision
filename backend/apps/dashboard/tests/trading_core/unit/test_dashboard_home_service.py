from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from apps.dashboard.application.trading_core.services.dashboard_home_service import (
    DashboardHomeService,
)
from apps.dashboard.domain.trading_core.exceptions import AccountSummaryNotInitialized


class TestDashboardHomeService:
    def test_get_summary_returns_dto(self) -> None:
        account_id = uuid4()
        mock_repo = MagicMock()
        mock_cache = MagicMock()
        mock_cache.get_summary.return_value = None

        mock_summary = MagicMock()
        mock_summary.account_id = account_id
        mock_summary.open_positions_count = 5
        mock_summary.open_orders_count = 3
        mock_summary.today_realized_pnl = Decimal("15000.00")
        mock_summary.today_unrealized_pnl = Decimal("5000.00")
        mock_summary.active_alerts_count = 2
        mock_summary.broker_connection_status = "connected"
        mock_summary.market_session_status = "open"
        mock_summary.projection_updated_at = None
        mock_repo.get.return_value = mock_summary

        service = DashboardHomeService(repository=mock_repo, cache=mock_cache)
        dto = service.get_summary(account_id)

        assert dto.account_id == account_id
        assert dto.open_positions_count == 5
        assert dto.today_realized_pnl == Decimal("15000.00")

    def test_get_summary_cache_hit(self) -> None:
        account_id = uuid4()
        mock_repo = MagicMock()
        mock_cache = MagicMock()
        mock_cache.get_summary.return_value = {
            "account_id": str(account_id),
            "open_positions_count": 5,
            "open_orders_count": 3,
            "today_realized_pnl": "15000.00",
            "today_unrealized_pnl": "5000.00",
            "active_alerts_count": 2,
            "broker_connection_status": "connected",
            "market_session_status": "open",
            "last_updated_at": None,
        }

        service = DashboardHomeService(repository=mock_repo, cache=mock_cache)
        dto = service.get_summary(account_id)

        assert dto.account_id == account_id
        assert dto.open_positions_count == 5
        mock_repo.get.assert_not_called()

    def test_get_summary_not_initialized(self) -> None:
        account_id = uuid4()
        mock_repo = MagicMock()
        mock_cache = MagicMock()
        mock_cache.get_summary.return_value = None
        mock_repo.get.side_effect = AccountSummaryNotInitialized(
            message="Not initialized",
            code="account_summary_not_initialized",
        )

        service = DashboardHomeService(repository=mock_repo, cache=mock_cache)
        with pytest.raises(AccountSummaryNotInitialized):
            service.get_summary(account_id)

    def test_get_summary_sets_cache(self) -> None:
        account_id = uuid4()
        mock_repo = MagicMock()
        mock_cache = MagicMock()
        mock_cache.get_summary.return_value = None

        mock_summary = MagicMock()
        mock_summary.account_id = account_id
        mock_summary.open_positions_count = 5
        mock_summary.open_orders_count = 3
        mock_summary.today_realized_pnl = Decimal("15000.00")
        mock_summary.today_unrealized_pnl = Decimal("5000.00")
        mock_summary.active_alerts_count = 2
        mock_summary.broker_connection_status = "connected"
        mock_summary.market_session_status = "open"
        mock_summary.projection_updated_at = None
        mock_repo.get.return_value = mock_summary

        service = DashboardHomeService(repository=mock_repo, cache=mock_cache)
        service.get_summary(account_id)

        mock_cache.set_summary.assert_called_once()
