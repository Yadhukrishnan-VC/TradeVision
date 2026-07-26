from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, PropertyMock, patch
from uuid import UUID, uuid4

import pytest
from django.utils import timezone

from apps.dashboard.application.analytics_risk.dto import PerformanceDTO, PnLSummaryDTO, RiskSummaryDTO
from apps.dashboard.application.analytics_risk.services import PnLAnalyticsService, PerformanceService, RiskService
from apps.dashboard.domain.analytics_risk.value_objects import Period


def make_mock_queryset(items: list) -> MagicMock:
    qs = MagicMock()
    qs.__iter__.return_value = iter(items)
    qs.__len__.return_value = len(items)
    qs.count.return_value = len(items)
    qs.first.return_value = items[0] if items else None
    qs.filter.return_value = qs
    qs.order_by.return_value = qs

    def values_side_effect(*args: str, **kwargs: str) -> MagicMock:
        return qs

    qs.values.side_effect = values_side_effect
    return qs


class TestPnLAnalyticsService:
    def test_get_summary_returns_dto(self) -> None:
        mock_snapshot_repo = MagicMock()
        mock_snapshot_repo.filter_by_date_range.return_value = make_mock_queryset([])

        service = PnLAnalyticsService(snapshot_repo=mock_snapshot_repo)

        result = service.get_summary(uuid4(), Period.ALL_TIME)
        assert isinstance(result, PnLSummaryDTO)
        assert result.current_total_pnl == Decimal("0")

    def test_get_daily_rollup_empty(self) -> None:
        mock_rollup_repo = MagicMock()
        mock_rollup_repo.filter_by_date_range.return_value = make_mock_queryset([])

        service = PnLAnalyticsService(rollup_repo=mock_rollup_repo)
        result = service.get_daily_rollup(
            uuid4(),
            date(2024, 1, 1),
            date(2024, 1, 31),
        )
        assert result == []


class TestPerformanceService:
    def test_get_metrics_returns_dto(self) -> None:
        mock_repo = MagicMock()
        mock_repo.get.return_value = None
        mock_cache = MagicMock()
        mock_cache.get_metrics.return_value = None

        account_id = uuid4()
        service = PerformanceService(repo=mock_repo, cache=mock_cache)

        result = service.get_metrics(account_id, Period.THIRTY_DAYS)
        assert isinstance(result, PerformanceDTO)
        assert result.total_trades == 0

    def test_get_metrics_uses_cache(self) -> None:
        mock_cache = MagicMock()
        mock_repo = MagicMock()

        account_id = uuid4()
        mock_cache.get_metrics.return_value = {
            "period": "30d",
            "win_rate": "0.5",
            "avg_win": "100",
            "avg_loss": "50",
            "profit_factor": "2.0",
            "expectancy": "25",
            "sharpe_like_ratio": "1.5",
            "total_trades": 10,
            "winning_trades": 5,
            "losing_trades": 5,
        }

        service = PerformanceService(repo=mock_repo, cache=mock_cache)
        result = service.get_metrics(account_id, Period.THIRTY_DAYS)

        assert result.total_trades == 10
        assert mock_repo.get.call_count == 0


class TestRiskService:
    def test_get_summary_empty(self) -> None:
        mock_metric_repo = MagicMock()
        mock_metric_repo.get_latest.return_value = None
        mock_alert_repo = MagicMock()
        mock_alert_repo.list_active.return_value = make_mock_queryset([])
        mock_cache = MagicMock()

        service = RiskService(metric_repo=mock_metric_repo, alert_repo=mock_alert_repo, cache=mock_cache)
        result = service.get_summary(uuid4())

        assert isinstance(result, RiskSummaryDTO)
        assert result.total_exposure == Decimal("0")

    def test_get_metric_history_empty(self) -> None:
        mock_metric_repo = MagicMock()
        mock_metric_repo.filter_by_date_range.return_value = make_mock_queryset([])

        service = RiskService(metric_repo=mock_metric_repo)
        result = service.get_metric_history(
            uuid4(),
            datetime(2024, 1, 1),
            datetime(2024, 1, 31),
        )
        assert result == []
