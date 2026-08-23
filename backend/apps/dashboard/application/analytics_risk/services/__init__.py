from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from django.conf import settings

from apps.dashboard.application.analytics_risk.dto import RiskSummaryDTO
from apps.dashboard.infrastructure.analytics_risk.cache import RiskLatestCache
from apps.dashboard.infrastructure.analytics_risk.repositories import RiskAlertProjectionRepository, RiskMetricSnapshotRepository
from apps.dashboard.infrastructure.common.event_log import DriftAlertRepository
from apps.live_drift.infrastructure.models import DriftAlert


class DriftAlertService:
    """Service for dashboard visibility of drift alert records."""

    def __init__(
        self,
        repo: DriftAlertRepository | None = None,
    ) -> None:
        self._repo = repo or DriftAlertRepository()

    def list_recent_alerts(self, limit: int = 50) -> list[dict]:
        """Return recent DriftAlert records for dashboard display."""
        return self._repo.list_recent(limit)

    def count_active_alerts(self) -> int:
        """Return count of un-notified drift alerts."""
        return self._repo.count_active()

    def list_rule_expectations_summary(self, account_id: UUID) -> list[dict]:
        """Return reconcile_rule_expectations output for a given account.

        This aggregates the daily expectations output so the dashboard can
        show rule-level win rates, expectancies, and trade counts.
        """
        from apps.portfolio_reconciliation.infrastructure.tasks import (
            reconcile_rule_expectations,
        )

        # Run a single window pass and return the structured output
        result = reconcile_rule_expectations(window_hours=24)
        return result.get("per_rule", [])

    def get_edge_validation_summary(self) -> dict:
        """Read-only render of EDGE_VALIDATION_REPORT_V2.md summary table.

        Returns the key metrics from the report as a dict for dashboard display.
        The report is read from ``docs/EDGE_VALIDATION_REPORT_V2.md`` at the
        repository root.
        """
        import os

        report_path = os.path.join(
            settings.BASE_DIR, "docs", "EDGE_VALIDATION_REPORT_V2.md",
        )
        fallback = os.path.join(
            settings.BASE_DIR, "backend", "docs", "EDGE_VALIDATION_REPORT_V2.md",
        )

        report_file = report_path if os.path.exists(report_path) else fallback

        if not os.path.exists(report_file):
            return {"error": "EDGE_VALIDATION_REPORT_V2.md not found}

        with open(report_file, "r") as fh:
            content = fh.read()

        # Extract the summary table - look for key metrics patterns
        summary = {"full_report": content}

        # Try to extract expectancy, symbol count, and survivor info
        import re

        # Find expectancy values
        expectancy_matches = re.findall(
            r"Expectancy[\s]+([+-]?\d*\.?\d+)",
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
            r"ADANIENT[^
]*",
            content,
        )
        if adanient_matches:
            summary["adanient_observations"] = adanient_matches

        return summary


class PerformanceServiceWrapper:
    """Wrapper that adds drift-aware context to the existing PerformanceService."""

    def __init__(
        self,
        base_service: PerformanceService | None = None,
        drift_service: DriftAlertService | None = None,
    ) -> None:
        self._base = base_service or PerformanceService()
        self._drift = drift_service or DriftAlertService()

    def get_dashboard_context(self, account_id: UUID) -> dict:
        """Combine performance metrics with drift alert context."""
        perf = self._base.get_summary(account_id)
        alerts = self._drift.count_active_alerts()
        recent = self._drift.list_recent_alerts(limit=10)

        return {
            "performance": {
                "win_rate": str(perf.win_rate),
                "expectancy": str(perf.expectancy),
                "total_trades": perf.total_trades,
            },
            "drift": {
                "active_alerts": alerts,
                "recent_alerts": recent,
            },
        }


__all__ = ["DriftAlertService", "PerformanceServiceWrapper"]
