from __future__ import annotations

from uuid import UUID

from django.db.models import QuerySet

from apps.dashboard.domain.trading_core.exceptions import (
    AccountSummaryNotInitialized,
    HoldingNotFound,
    OrderNotFound,
    PortfolioNotInitialized,
    PositionNotFound,
    TradeRecordNotFound,
)
from apps.dashboard.infrastructure.trading_core.models import (
    DashboardHomeSummary,
    ExportJob,
    Holding,
    OrderSnapshot,
    PositionSnapshot,
    TradeRecord,
)


class PositionSnapshotRepository:
    def get(self, account_id: UUID, position_id: UUID) -> PositionSnapshot:
        try:
            return PositionSnapshot.objects.get(account_id=account_id, position_id=position_id)
        except PositionSnapshot.DoesNotExist:
            raise PositionNotFound(
                message=f"Position {position_id} not found for account {account_id}",
                code="position_not_found",
            )

    def list_open(self, account_id: UUID) -> QuerySet[PositionSnapshot]:
        return PositionSnapshot.objects.filter(account_id=account_id, is_open=True)

    def filter_open(self, account_id: UUID, **filters: object) -> QuerySet[PositionSnapshot]:
        qs = self.list_open(account_id)
        for key, value in filters.items():
            if value is not None:
                qs = qs.filter(**{key: value})
        return qs

    def exists(self, position_id: UUID) -> bool:
        return PositionSnapshot.objects.filter(position_id=position_id).exists()


class OrderSnapshotRepository:
    def get(self, account_id: UUID, order_id: UUID) -> OrderSnapshot:
        try:
            return OrderSnapshot.objects.get(account_id=account_id, order_id=order_id)
        except OrderSnapshot.DoesNotExist:
            raise OrderNotFound(
                message=f"Order {order_id} not found for account {account_id}",
                code="order_not_found",
            )

    def list_all(self, account_id: UUID) -> QuerySet[OrderSnapshot]:
        return OrderSnapshot.objects.filter(account_id=account_id)

    def filter_all(self, account_id: UUID, **filters: object) -> QuerySet[OrderSnapshot]:
        qs = self.list_all(account_id)
        for key, value in filters.items():
            if value is not None:
                qs = qs.filter(**{key: value})
        return qs

    def exists(self, order_id: UUID) -> bool:
        return OrderSnapshot.objects.filter(order_id=order_id).exists()


class TradeRecordRepository:
    def list_all(self, account_id: UUID) -> QuerySet[TradeRecord]:
        return TradeRecord.objects.filter(account_id=account_id)

    def filter_all(self, account_id: UUID, **filters: object) -> QuerySet[TradeRecord]:
        qs = self.list_all(account_id)
        for key, value in filters.items():
            if value is not None:
                qs = qs.filter(**{key: value})
        return qs

    def exists_by_last_event_id(self, last_event_id: UUID) -> bool:
        return TradeRecord.objects.filter(last_event_id=last_event_id).exists()


class HoldingRepository:
    def get(self, account_id: UUID, symbol: str) -> Holding:
        try:
            return Holding.objects.get(account_id=account_id, symbol=symbol)
        except Holding.DoesNotExist:
            raise HoldingNotFound(
                message=f"Holding {symbol} not found for account {account_id}",
                code="holding_not_found",
            )

    def list_all(self, account_id: UUID) -> QuerySet[Holding]:
        return Holding.objects.filter(account_id=account_id)

    def list_active(self, account_id: UUID) -> QuerySet[Holding]:
        return Holding.objects.filter(account_id=account_id, quantity__gt=0)

    def exists(self, account_id: UUID, symbol: str) -> bool:
        return Holding.objects.filter(account_id=account_id, symbol=symbol).exists()


class DashboardHomeSummaryRepository:
    def get(self, account_id: UUID) -> DashboardHomeSummary:
        try:
            return DashboardHomeSummary.objects.get(pk=account_id)
        except DashboardHomeSummary.DoesNotExist:
            raise AccountSummaryNotInitialized(
                message=f"Dashboard home summary not initialized for account {account_id}",
                code="account_summary_not_initialized",
            )

    def exists(self, account_id: UUID) -> bool:
        return DashboardHomeSummary.objects.filter(pk=account_id).exists()


class ExportJobRepository:
    def get(self, export_id: UUID) -> ExportJob:
        try:
            return ExportJob.objects.get(pk=export_id)
        except ExportJob.DoesNotExist:
            raise TradeRecordNotFound(
                message=f"Export job {export_id} not found",
                code="export_job_not_found",
            )

    def create(self, **kwargs: object) -> ExportJob:
        return ExportJob.objects.create(**kwargs)

    def update(self, export_id: UUID, **kwargs: object) -> ExportJob:
        ExportJob.objects.filter(pk=export_id).update(**kwargs)
        return self.get(export_id)
