from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from django.test import TestCase

from apps.dashboard.infrastructure.analytics_risk.models import (
    PnLDailyRollup,
    PnLSnapshot,
    PerformanceSnapshot,
    RiskAlertProjection,
    RiskMetricSnapshot,
)
from apps.dashboard.infrastructure.analytics_risk.repositories import (
    PnLDailyRollupRepository,
    PnLSnapshotRepository,
    PerformanceSnapshotRepository,
    RiskAlertProjectionRepository,
    RiskMetricSnapshotRepository,
)


class TestPnLSnapshotRepository(TestCase):
    def setUp(self) -> None:
        self.repo = PnLSnapshotRepository()
        self.account_id = uuid4()

    def test_filter_by_date_range_empty(self) -> None:
        qs = self.repo.filter_by_date_range(
            self.account_id,
            "2024-01-01T00:00:00Z",
            "2024-01-31T00:00:00Z",
        )
        assert qs.count() == 0

    def test_get_latest_empty(self) -> None:
        assert self.repo.get_latest(self.account_id) is None

    def test_count_in_range_empty(self) -> None:
        count = self.repo.count_in_range(
            self.account_id,
            "2024-01-01T00:00:00Z",
            "2024-01-31T00:00:00Z",
        )
        assert count == 0


class TestPnLDailyRollupRepository(TestCase):
    def setUp(self) -> None:
        self.repo = PnLDailyRollupRepository()
        self.account_id = uuid4()

    def test_filter_by_date_range_empty(self) -> None:
        qs = self.repo.filter_by_date_range(
            self.account_id,
            "2024-01-01",
            "2024-01-31",
        )
        assert qs.count() == 0

    def test_exists_for_date_false(self) -> None:
        assert self.repo.exists_for_date(self.account_id, "2024-01-01") is False


class TestPerformanceSnapshotRepository(TestCase):
    def setUp(self) -> None:
        self.repo = PerformanceSnapshotRepository()
        self.account_id = uuid4()

    def test_get_missing(self) -> None:
        assert self.repo.get(self.account_id, "30d") is None

    def test_upsert_creates(self) -> None:
        obj = self.repo.upsert(self.account_id, "30d", total_trades=10)
        assert obj.total_trades == 10

    def test_upsert_updates(self) -> None:
        self.repo.upsert(self.account_id, "30d", total_trades=10)
        obj = self.repo.upsert(self.account_id, "30d", total_trades=20)
        assert obj.total_trades == 20


class TestRiskMetricSnapshotRepository(TestCase):
    def setUp(self) -> None:
        self.repo = RiskMetricSnapshotRepository()
        self.account_id = uuid4()

    def test_get_latest_empty(self) -> None:
        assert self.repo.get_latest(self.account_id) is None

    def test_filter_by_date_range_empty(self) -> None:
        qs = self.repo.filter_by_date_range(
            self.account_id,
            "2024-01-01T00:00:00Z",
            "2024-01-31T00:00:00Z",
        )
        assert qs.count() == 0


class TestRiskAlertProjectionRepository(TestCase):
    def setUp(self) -> None:
        self.repo = RiskAlertProjectionRepository()
        self.account_id = uuid4()

    def test_list_active_empty(self) -> None:
        qs = self.repo.list_active(self.account_id)
        assert qs.count() == 0

    def test_list_all_empty(self) -> None:
        qs = self.repo.list_all(self.account_id)
        assert qs.count() == 0
