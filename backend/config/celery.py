"""
TradeVision AI — Celery application and queue configuration.

Named queues map to dedicated worker pools, allowing independent scaling
and prioritisation per workload type. See docker-compose.yml for the
worker pool assignments.
"""

import os

from celery import Celery
from kombu import Exchange, Queue

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = Celery("tradevision")

# Read configuration from Django settings (CELERY_* namespace)
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all INSTALLED_APPS
app.autodiscover_tasks()

# ---------------------------------------------------------------------------
# Named queues — one per logical workload domain
# Each queue has a dedicated direct exchange to prevent cross-queue routing.
# ---------------------------------------------------------------------------
_QUEUE_NAMES: tuple[str, ...] = (
    "market_data",    # tick ingestion, OHLCV polling
    "processing",     # indicator computation, NLP, options analysis
    "intelligence",   # IntelligencePacket assembly
    "rule_engine",    # deterministic rule evaluation
    "ai",             # AI provider calls (rate-limited worker pool)
    "notifications",  # WebSocket push, email, push delivery
    "analytics",      # backtesting, calibration, EOD aggregation
    "default",        # miscellaneous background work
)

app.conf.task_queues = [
    Queue(
        name=queue_name,
        exchange=Exchange(queue_name, type="direct"),
        routing_key=queue_name,
        durable=True,
    )
    for queue_name in _QUEUE_NAMES
]

app.conf.task_default_queue = "default"
app.conf.task_default_exchange = "default"
app.conf.task_default_routing_key = "default"

# ---------------------------------------------------------------------------
# Debug task — verifies Celery workers are alive during development
# ---------------------------------------------------------------------------
@app.task(bind=True, name="tradevision.debug_task")
def debug_task(self) -> str:  # type: ignore[misc]
    """Return worker identity — used in health checks and smoke tests."""
    return f"Request: {self.request!r}"
