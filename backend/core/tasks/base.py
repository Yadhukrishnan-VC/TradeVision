"""
TradeVision AI — Celery base task with structured logging and correlation IDs.

Every Celery task in the project should set ``base=BaseTask``. This provides:
    - Automatic correlation ID binding to the structlog context
    - Structured ``task_started`` / ``task_completed`` / ``task_failed`` events
    - Wall-clock timing recorded in milliseconds
    - A static helper for constructing deterministic idempotency keys

Retry constants are module-level so they can be imported independently::

    from core.tasks.base import AI_MAX_RETRIES, DEFAULT_RETRY_DELAY
"""

import logging
import time
from typing import Any

from celery import Task

from core.logging import bind_context, clear_context, get_logger
from core.utils import generate_correlation_id

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Retry constants — import and use in task decorators for consistency
# ---------------------------------------------------------------------------

DEFAULT_MAX_RETRIES: int = 3
"""Standard maximum retry count for most task queues."""

DEFAULT_RETRY_DELAY: int = 60
"""Seconds between retry attempts for standard tasks."""

DEFAULT_RETRY_BACKOFF: float = 2.0
"""Exponential backoff multiplier applied between retries."""

AI_MAX_RETRIES: int = 5
"""Higher retry count for the AI queue — provider calls may be intermittently slow."""

AI_RETRY_DELAY: int = 120
"""Longer retry delay for AI tasks to avoid hammering a rate-limited provider."""

INGESTION_MAX_RETRIES: int = 3
"""Standard retry count for market data ingestion tasks."""

INGESTION_RETRY_DELAY: int = 30
"""Short retry delay for ingestion tasks — stale data must be recovered quickly."""

NOTIFICATION_MAX_RETRIES: int = 5
"""Higher retry count for notification delivery — user-facing, must not be dropped."""

NOTIFICATION_RETRY_DELAY: int = 10
"""Short retry delay for notifications — time-sensitive delivery."""


# ---------------------------------------------------------------------------
# Base task
# ---------------------------------------------------------------------------


class BaseTask(Task):
    """
    Abstract Celery base task providing structured logging and correlation IDs.

    Set ``base=BaseTask`` on any task that should participate in request
    tracing. The correlation ID is read from ``kwargs["correlation_id"]``
    if present, or generated fresh for tasks that are scheduled by Celery
    Beat or triggered without an explicit correlation context.

    Hooks used:
        ``before_start`` — binds correlation ID and records start time
        ``after_return``  — logs completion with duration and clears context
        ``on_failure``    — logs failure details at ERROR level

    Example::

        @app.task(base=BaseTask, bind=True, max_retries=AI_MAX_RETRIES)
        def call_ai_provider(self, request_id: str, correlation_id: str = "") -> None:
            ...
    """

    abstract: bool = True

    def before_start(
        self,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        """
        Bind correlation ID and record the task start time.

        Called immediately before ``run()`` executes. The start time is stored
        as an instance attribute so ``after_return`` can compute duration.

        Args:
            task_id: Celery-assigned task UUID.
            args:    Positional task arguments.
            kwargs:  Keyword task arguments (may include ``correlation_id``).
        """
        correlation_id: str = kwargs.get("correlation_id") or generate_correlation_id()
        bind_context(
            correlation_id=correlation_id,
            task_id=task_id,
            task_name=self.name or "",
        )
        self._task_start_time: float = time.monotonic()

        logger.info(
            "task_started",
            extra={
                "task_name": self.name,
                "task_id": task_id,
                "correlation_id": correlation_id,
            },
        )

    def after_return(
        self,
        status: str,
        retval: Any,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        """
        Log task completion with duration and clear the structlog context.

        Called after the task returns regardless of success or failure.

        Args:
            status:  Celery task status string (e.g. ``"SUCCESS"``, ``"FAILURE"``).
            retval:  Return value or exception instance.
            task_id: Celery-assigned task UUID.
            args:    Positional task arguments.
            kwargs:  Keyword task arguments.
            einfo:   Exception info object (``None`` on success).
        """
        start: float = getattr(self, "_task_start_time", time.monotonic())
        duration_ms: float = round((time.monotonic() - start) * 1000, 2)

        logger.info(
            "task_completed",
            extra={
                "task_name": self.name,
                "task_id": task_id,
                "status": status,
                "duration_ms": duration_ms,
            },
        )
        clear_context()

    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        """
        Log unhandled task failure at ERROR level.

        Called when the task raises an exception that is not retried.

        Args:
            exc:     The exception that caused the failure.
            task_id: Celery-assigned task UUID.
            args:    Positional task arguments.
            kwargs:  Keyword task arguments.
            einfo:   Formatted exception traceback info.
        """
        logger.error(
            "task_failed",
            exc_info=exc,
            extra={
                "task_name": self.name,
                "task_id": task_id,
                "exception_type": type(exc).__name__,
            },
        )

    @staticmethod
    def make_idempotency_key(*parts: str) -> str:
        """
        Construct a deterministic, namespaced idempotency key.

        Joins ``parts`` with ``:`` and prepends the ``idempotency:`` namespace.
        Suitable for use as a Redis key to detect duplicate task executions.

        Args:
            *parts: String components to compose the key from (e.g. symbol,
                    event type, timestamp truncated to the minute).

        Returns:
            A string key in the form ``"idempotency:part1:part2:…"``.

        Example::

            key = BaseTask.make_idempotency_key("RELIANCE", "price_movement", "2024-01-15T09:30")
            # → "idempotency:RELIANCE:price_movement:2024-01-15T09:30"
        """
        return "idempotency:" + ":".join(str(p) for p in parts)
