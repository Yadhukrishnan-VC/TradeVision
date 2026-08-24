from __future__ import annotations

from .pnl_analytics_service import PnLAnalyticsService
from .performance_service import PerformanceService
from .risk_service import RiskService

__all__ = [
    "PnLAnalyticsService",
    "PerformanceService",
    "RiskService",
]

from datetime import datetime
from decimal import Decimal
from uuid import UUID

import os
import re

from django.conf import settings

from apps.dashboard.application.analytics_risk.dto import RiskSummaryDTO
from apps.dashboard.infrastructure.analytics_risk.cache import RiskLatestCache
from apps.dashboard.infrastructure.analytics_risk.repositories import RiskAlertProjectionRepository, RiskMetricSnapshotRepository
from apps.dashboard.infrastructure.common.event_log import DriftAlertRepository
from apps.live_drift.infrastructure.models import DriftAlert


class DriftAlertService:
    """Service for dashboard visibility of drift alert records."""

    def __init__(self, repo: DriftAlertRepository | None = None) -> None:
        self._repo = repo or DriftAlertRepository()

    def list_recent_alerts(self, limit: int = 50) -> list[dict]:
        """Return recent DriftAlert records for dashboard display."""
        return self._repo.list_recent(limit)

    def count_active_alerts(self) -> int:
        """Return count of un-notified drift alerts."""
        return self._repo.count_active()

    def list_rule_expectations_summary(self, account_id: UUID) -> list[dict]:
        """Return reconcile_rule_expectations output for a given account."""
        from apps.portfolio_reconciliation.infrastructure.tasks import (
            reconcile_rule_expectations,
        )
        result = reconcile_rule_expectations(window_hours=24)
        return result.get("per_rule", [])


class EdgeValidationReportService:
    """Read-only render of EDGE_VALIDATION_REPORT_V2.md summary table."""

    def get_edge_validation_summary(self) -> dict:
        """Read-only render of EDGE_VALIDATION_REPORT_V2.md summary table."""
        import re

        report_path = os.path.join(
            settings.BASE_DIR, "docs", "EDGE_VALIDATION_REPORT_V2.md",
        )
        fallback = os.path.join(
            settings.BASE_DIR, "backend", "docs", "EDGE_VALIDATION_REPORT_V2.md",
        )

        report_file = report_path if os.path.exists(report_path) else fallback

        if not os.path.exists(report_file):
            return {"error": "EDGE_VALIDATION_REPORT_V2.md not found"}

        with open(report_file, "r") as fh:
            content = fh.read()

        summary = {"full_report": content}

        # Extract expectancy values
        expectancy_matches = re.findall(
            r"Expectancy\s+([+-]?\d*\.?\d+)",
            content,
        )
        if expectancy_matches:
            summary["expectancies"] = expectancy_matches

        # Find survivor count
        survivor_matches = re.findall(
            r"(\d+)/(\d+)\s+NIFTY50",
            content,
        )
        if survivor_matches:
            summary["survivor_ratio"] = {
                "survivors": int(survivor_matches[0][0]),
                "total": int(survivor_matches[0][1]),
            }

        # Find ADANIENT flipped info
        adanient_matches = re.findall(
            r"ADANIENT[^\n]*",
            content,
        )
        if adanient_matches:
            summary["adanient_observations"] = adanient_matches

        return summary


__all__ = ["DriftAlertService", "EdgeValidationReportService"]
