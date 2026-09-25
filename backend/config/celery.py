from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("tradevision")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()

# Task modules live under app/*/infrastructure/ and other nested packages, which
# Celery's autodiscover_tasks() does not scan. Import them explicitly so every
# worker registers all task names; QUEUE_ROUTES + per-worker --queues still
# decide which worker actually consumes a given task.
app.conf.update(
    imports=(
        "apps.accounts.infrastructure.tasks",
        "apps.ai_engine.tasks",
        "apps.backtesting.infrastructure.tasks",
        "apps.dashboard.tasks.analytics_risk",
        "apps.dashboard.tasks.trading_core_tasks",
        "apps.eventbus.infrastructure.tasks",
        "apps.execution.infrastructure.broker_connection_status",
        "apps.execution.infrastructure.tasks",
        "apps.ingestion.infrastructure.tasks",
        "apps.journal.infrastructure.tasks",
        "apps.live_drift.infrastructure.tasks",
        "apps.macro_context.infrastructure.tasks",
        "apps.market_data.infrastructure.polling_tasks",
        "apps.market_data.infrastructure.tasks",
        "apps.news_feed.infrastructure.tasks",
        "apps.pattern_engine.infrastructure.tasks",
        "apps.pipeline_health.infrastructure.tasks",
        "apps.portfolio_reconciliation.infrastructure.tasks",
        "apps.recommendations.infrastructure.tasks",
        "apps.recommendations.tasks",
        "apps.risk_management.infrastructure.tasks",
        "apps.rule_engine.infrastructure.tasks",
        "apps.strategy_registry.tasks",
        "apps.trader_memory.infrastructure.tasks",
    )
)

QUEUE_ROUTES: dict[str, str] = {
    "apps.webhooks": "webhooks",
    "apps.signals_engine": "signals",
    "apps.analysis": "analysis",
    "apps.ai_reasoning": "ai_reasoning",
    "apps.decisions": "decisions",
    "apps.execution_engine": "execution",
    "apps.execution": "execution",
    "apps.monitoring": "monitoring",
    "apps.portfolio": "portfolio",
    "apps.analytics": "analytics",
    "apps.notifications": "notifications",
    "apps.eventbus": "maintenance",
    "apps.accounts": "maintenance",
    "apps.market_data": "market_data",
    "apps.ingestion": "webhooks",
}


def route_task(name: str, args: list, kwargs: dict) -> dict[str, str] | None:
    for prefix, queue in QUEUE_ROUTES.items():
        if name.startswith(prefix):
            return {"queue": queue}
    return None


app.conf.task_create_missing_queues = True
