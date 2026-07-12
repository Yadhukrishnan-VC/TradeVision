"""
TradeVision AI — Celery base task class.

``BaseTask`` extends ``celery.Task`` to provide structured logging, correlation
ID binding, timing instrumentation, and standard retry constants for all
TradeVision Celery tasks.
"""

import time
from typing import Any

from celery import Task

from core.logging import get_logger, bind_context, clear_context
from core.utils import generate_correlation_id, get_now


class BaseTask(Task):
    """
    Base class for all TradeVision Celery tasks.

    Provides:
        - Automatic correlation ID binding per task execution
        - Structured logging via ``self.logger``
        - Timing instrumentation (task duration logged on completion)
        - Standard retry constants
        - Idempotency key helper
    """

    name: str = "tradevision.base"
    max_retries: int = 3
    default_retry_delay: int = 60
    autoretry_for: tuple[type[Exception], ...] = ()
    retry_backoff: bool = True
    retry_backoff_max: int = 300
    retry_jitter: bool = True

    def __init__(self) -> None:
        super().__init__()
        self.logger = get_logger(self.__name__)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Wrap task execution with correlation ID, logging, and timing."""
        correlation_id = generate_correlation_id()
        bind_context(correlation_id=correlation_id, task_name=self.name)

        start = time.monotonic()
        self.logger.info(
            "task_started",
            extra={"task_name": self.name, "correlation_id": correlation_id},
        )

        try:
            result = super().__call__(*args, **kwargs)
            duration_ms = (time.monotonic() - start) * 1000
            self.logger.info(
                "task_completed",
                extra={
                    "task_name": self.name,
                    "correlation_id": correlation_id,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            return result
        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000
            self.logger.error(
                "task_failed",
                extra={
                    "task_name": self.name,
                    "correlation_id": correlation_id,
                    "duration_ms": round(duration_ms, 2),
                    "error": str(exc),
                },
            )
            raise
        finally:
            clear_context()

    @staticmethod
    def idempotency_key(*parts: Any) -> str:
        """
        Generate a deterministic idempotency key from the given parts.

        Useful for deduplicating task executions::

            key = BaseTask.idempotency_key("ingest", symbol, "2024-03-17T10:00:00")
        """
        return ":".join(str(p) for p in parts)
