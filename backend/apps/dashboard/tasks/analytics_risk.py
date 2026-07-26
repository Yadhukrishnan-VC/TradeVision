from __future__ import annotations

from uuid import UUID

from apps.dashboard.application.analytics_risk.services import PnLAnalyticsService, PerformanceService, RiskService
from core.celery import app


@app.task(bind=True, max_retries=3, default_retry_delay=60)
def refresh_pnl_snapshot_cache(self: object, account_id: str) -> None:
    from apps.dashboard.domain.analytics_risk.value_objects import Period

    service = PnLAnalyticsService()
    for period in Period:
        service.get_summary(UUID(account_id), period)


@app.task(bind=True, max_retries=3, default_retry_delay=60)
def refresh_performance_cache(self: object, account_id: str) -> None:
    from apps.dashboard.domain.analytics_risk.value_objects import Period

    service = PerformanceService()
    for period in Period:
        service.get_metrics(UUID(account_id), period)


@app.task(bind=True, max_retries=3, default_retry_delay=60)
def refresh_risk_cache(self: object, account_id: str) -> None:
    service = RiskService()
    service.get_summary(UUID(account_id))
