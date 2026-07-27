from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("tradevision")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()

QUEUE_ROUTES: dict[str, str] = {
    "apps.webhooks": "webhooks",
    "apps.signals_engine": "signals",
    "apps.analysis": "analysis",
    "apps.ai_reasoning": "ai_reasoning",
    "apps.decisions": "decisions",
    "apps.execution_engine": "execution",
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
