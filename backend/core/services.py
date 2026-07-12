"""
TradeVision AI — Base service class.

All application service classes (``apps/<app>/services.py``) inherit from
``BaseService`` to receive:
    - A structured logger bound to the subclass's module and class name
    - Convenience methods for structlog context management
    - A correlation ID generator

Service classes must not import from ``core.repository`` or perform any
database access directly — that responsibility belongs to repository classes
which are injected or accessed via ``self._repository``.

Business logic must never reside in views, serialisers, models, or tasks.
"""

import logging
from typing import Any

from core.logging import bind_context, clear_context, get_logger
from core.utils import generate_correlation_id


class BaseService:
    """
    Abstract base for all TradeVision AI service classes.

    Provides a pre-configured structured logger, context management helpers,
    and a correlation ID generator. Subclasses should call ``super().__init__()``
    to ensure the logger is initialised.

    Example::

        class MarketDataService(BaseService):
            def __init__(self, repository: MarketDataRepository) -> None:
                super().__init__()
                self._repository = repository

            def get_latest_tick(self, symbol: str) -> Tick | None:
                self._logger.info("fetching_latest_tick", extra={"symbol": symbol})
                return self._repository.get_latest_by_symbol(symbol)
    """

    def __init__(self) -> None:
        self._logger = get_logger(
            f"{self.__class__.__module__}.{self.__class__.__name__}"
        )

    def bind_context(self, **kwargs: Any) -> None:
        """
        Bind key-value pairs to the current structlog context.

        Bound values are automatically included in every subsequent log call
        within the same request or task context. Use for attaching ``symbol``,
        ``user_id``, ``correlation_id``, or other per-request context.

        Args:
            **kwargs: Arbitrary key-value pairs to add to the log context.
        """
        bind_context(**kwargs)

    def clear_context(self) -> None:
        """
        Clear all values bound to the current structlog context.

        Call at the end of a request, task, or unit of work to prevent
        context values from leaking into subsequent operations on the same
        thread or async task.
        """
        clear_context()

    def generate_correlation_id(self) -> str:
        """
        Generate a fresh UUID4 string for use as a correlation ID.

        Returns:
            A hyphen-separated UUID4 string, e.g.
            ``"3fa85f64-5717-4562-b3fc-2c963f66afa6"``.
        """
        return generate_correlation_id()
