"""
TradeVision AI — Structured logging configuration.

Configures structlog with a processor chain that:
  - Adds log level, timestamp, and logger name
  - Binds a correlation_id to every entry in a request/task context
  - Renders JSON output in production, coloured console output in development
  - Bridges structlog and the stdlib logging configured in Django settings

Usage::

    from core.logging import get_logger, bind_context

    logger = get_logger(__name__)
    logger.info("tick_ingested", symbol="RELIANCE", interval="1min")

    # Bind context that flows through all log calls in a request/task:
    bind_context(correlation_id="abc-123", user_id="u-456")
"""

import logging as _stdlib_logging
import sys
from typing import Any

import structlog

# Processors that run on every log event regardless of environment
_SHARED_PROCESSORS: list[Any] = [
    # Merge _contextvars context (set via bind_context) into the event dict
    structlog.contextvars.merge_contextvars,
    # Add log level as a string ("info", "warning", …)
    structlog.stdlib.add_log_level,
    # Add the logger name
    structlog.stdlib.add_logger_name,
    # ISO-8601 UTC timestamp
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    # Render exception tracebacks when exc_info is provided
    structlog.processors.StackInfoRenderer(),
]


def configure_structlog(*, development: bool = False) -> None:
    """
    Configure structlog.

    Called once from apps.common.apps.CommonConfig.ready().

    Args:
        development: When True, renders coloured output for humans.
                     When False, renders JSON for log aggregation systems.
    """
    if development:
        renderer: Any = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *_SHARED_PROCESSORS,
            # Format exceptions as strings before final rendering
            structlog.processors.format_exc_info,
            renderer,
        ],
        # Use stdlib logger as the underlying output so Django's LOGGING
        # configuration controls handlers, levels, and destinations.
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Also configure the stdlib → structlog bridge so that third-party
    # libraries that use stdlib logging are processed through structlog.
    _stdlib_logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=_stdlib_logging.WARNING,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Return a structlog logger bound to the given name.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A structlog BoundLogger that emits structured JSON in production
        and coloured text in development.
    """
    return structlog.get_logger(name)


def bind_context(**kwargs: Any) -> None:
    """
    Bind key-value pairs to the current async/thread context.

    Bound values are automatically included in every subsequent log call
    within the same request, task, or coroutine context.

    Common keys:
        correlation_id: UUID string for tracing a request end-to-end
        user_id:        Authenticated user's UUID
        symbol:         Stock symbol being processed
        task_id:        Celery task ID

    Example::

        bind_context(correlation_id="abc-123", symbol="INFY")
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """
    Clear all context variables bound in the current context.

    Call this at the end of a request or task to prevent context leakage
    between requests on the same thread.
    """
    structlog.contextvars.clear_contextvars()
