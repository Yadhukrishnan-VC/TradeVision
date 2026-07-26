from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from apps.dashboard.application.trading_core.dto import DashboardHomeSummaryDTO
from apps.dashboard.infrastructure.trading_core.cache import DashboardHomeCache
from apps.dashboard.infrastructure.trading_core.repositories import DashboardHomeSummaryRepository


class DashboardHomeService:
    def __init__(
        self,
        repository: DashboardHomeSummaryRepository | None = None,
        cache: DashboardHomeCache | None = None,
    ) -> None:
        self._repository = repository or DashboardHomeSummaryRepository()
        self._cache = cache or DashboardHomeCache()

    def get_summary(self, account_id: UUID) -> DashboardHomeSummaryDTO:
        cached = self._cache.get_summary(account_id)
        if cached is not None:
            return self._dto_from_dict(account_id, cached)

        summary = self._repository.get(account_id)
        dto = self._dto_from_model(summary)
        self._cache.set_summary(account_id, self._dto_to_dict(dto))
        return dto

    @staticmethod
    def _dto_from_model(summary: object) -> DashboardHomeSummaryDTO:
        return DashboardHomeSummaryDTO(
            account_id=summary.account_id,
            open_positions_count=summary.open_positions_count,
            open_orders_count=summary.open_orders_count,
            today_realized_pnl=summary.today_realized_pnl,
            today_unrealized_pnl=summary.today_unrealized_pnl,
            active_alerts_count=summary.active_alerts_count,
            broker_connection_status=summary.broker_connection_status,
            market_session_status=summary.market_session_status,
            last_updated_at=summary.projection_updated_at,
        )

    @staticmethod
    def _dto_to_dict(dto: DashboardHomeSummaryDTO) -> dict:
        return {
            "account_id": str(dto.account_id),
            "open_positions_count": dto.open_positions_count,
            "open_orders_count": dto.open_orders_count,
            "today_realized_pnl": str(dto.today_realized_pnl),
            "today_unrealized_pnl": str(dto.today_unrealized_pnl),
            "active_alerts_count": dto.active_alerts_count,
            "broker_connection_status": dto.broker_connection_status,
            "market_session_status": dto.market_session_status,
            "last_updated_at": dto.last_updated_at.isoformat() if dto.last_updated_at else None,
        }

    @staticmethod
    def _dto_from_dict(account_id: UUID, data: dict) -> DashboardHomeSummaryDTO:
        return DashboardHomeSummaryDTO(
            account_id=account_id,
            open_positions_count=data.get("open_positions_count", 0),
            open_orders_count=data.get("open_orders_count", 0),
            today_realized_pnl=Decimal(str(data.get("today_realized_pnl", "0"))),
            today_unrealized_pnl=Decimal(str(data.get("today_unrealized_pnl", "0"))),
            active_alerts_count=data.get("active_alerts_count", 0),
            broker_connection_status=data.get("broker_connection_status", "disconnected"),
            market_session_status=data.get("market_session_status", "closed"),
            last_updated_at=None,
        )
