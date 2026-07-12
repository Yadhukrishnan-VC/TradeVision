"""
TradeVision AI — Celery task foundation package.

Exports:
    BaseTask             — Abstract Celery task with structured logging and
                           correlation ID tracking
    DEFAULT_MAX_RETRIES  — Standard retry count for most queues
    AI_MAX_RETRIES       — Higher retry count for the AI queue
    QueueName            — Re-exported for task routing convenience

Usage::

    from core.tasks.base import BaseTask, DEFAULT_MAX_RETRIES
    from config.celery import app

    @app.task(base=BaseTask, bind=True)
    def my_task(self, symbol: str, correlation_id: str = "") -> None:
        ...
"""
