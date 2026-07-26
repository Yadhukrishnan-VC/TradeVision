from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from django.db.models import QuerySet

from apps.dashboard.infrastructure.analytics_risk.models import (
    PnLDailyRollup,
    PnLSnapshot,
    PerformanceSnapshot,
    RiskAlertProjection,
    RiskMetricSnapshot,
)


class PnLSnapshotRepository:
    def filter_by_date_range(
        self, account_id: UUID, date_from: datetime, date_to: datetime
    ) -> QuerySet[PnLSnapshot]:
        return PnLSnapshot.objects.filter(
            account_id=account_id,
            snapshot_at__gte=date_from,
            snapshot_at__lte=date_to,
        ).order_by("-snapshot_at")

    def get_latest(self, account_id: UUID) -> PnLSnapshot | None:
        return PnLSnapshot.objects.filter(account_id=account_id).order_by("-snapshot_at").first()

    def count_in_range(self, account_id: UUID, date_from: datetime, date_to: datetime) -> int:
        return PnLSnapshot.objects.filter(
            account_id=account_id,
            snapshot_at__gte=date_from,
            snapshot_at__lte=date_to,
        ).count()


class PnLDailyRollupRepository:
    def filter_by_date_range(
        self, account_id: UUID, date_from: date, date_to: date
    ) -> QuerySet[PnLDailyRollup]:
        return PnLDailyRollup.objects.filter(
            account_id=account_id,
            trading_date__gte=date_from,
            trading_date__lte=date_to,
        ).order_by("-trading_date")

    def exists_for_date(self, account_id: UUID, trading_date: date) -> bool:
        return PnLDailyRollup.objects.filter(
            account_id=account_id, trading_date=trading_date
        ).exists()


class PerformanceSnapshotRepository:
    def get(self, account_id: UUID, period: str) -> PerformanceSnapshot | None:
        try:
            return PerformanceSnapshot.objects.get(account_id=account_id, period=period)
        except PerformanceSnapshot.DoesNotExist:
            return None

    def upsert(self, account_id: UUID, period: str, **kwargs: object) -> PerformanceSnapshot:
        obj, _ = PerformanceSnapshot.objects.update_or_create(
            account_id=account_id,
            period=period,
            defaults=kwargs,
        )
        return obj


class RiskMetricSnapshotRepository:
    def filter_by_date_range(
        self, account_id: UUID, date_from: datetime, date_to: datetime
    ) -> QuerySet[RiskMetricSnapshot]:
        return RiskMetricSnapshot.objects.filter(
            account_id=account_id,
            snapshot_at__gte=date_from,
            snapshot_at__lte=date_to,
        ).order_by("-snapshot_at")

    def get_latest(self, account_id: UUID) -> RiskMetricSnapshot | None:
        return RiskMetricSnapshot.objects.filter(account_id=account_id).order_by("-snapshot_at").first()


class RiskAlertProjectionRepository:
    def list_active(self, account_id: UUID) -> QuerySet[RiskAlertProjection]:
        return RiskAlertProjection.objects.filter(
            account_id=account_id, resolved_at__isnull=True
        ).order_by("-raised_at")

    def list_all(self, account_id: UUID) -> QuerySet[RiskAlertProjection]:
        return RiskAlertProjection.objects.filter(account_id=account_id).order_by("-raised_at")
