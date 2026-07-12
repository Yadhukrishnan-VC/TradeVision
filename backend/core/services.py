"""
TradeVision AI — Base service class.

Provides ``BaseService`` with structured logging and correlation ID helpers
that all app-level services should inherit from.
"""

from typing import Any

from core.logging import get_logger, bind_context, clear_context
from core.utils import generate_correlation_id


class BaseService:
    """
    Base class for all TradeVision services.

    Provides:
        - A structured logger (``self.logger``)
        - Correlation ID bind/clear helpers
    """

    def __init__(self) -> None:
        self.logger = get_logger(self.__class__.__module__)

    def bind_correlation(self, correlation_id: str | None = None) -> str:
        """
        Bind a correlation ID to the current context.

        Args:
            correlation_id: If None, generates a new UUID4.

        Returns:
            The bound correlation ID.
        """
        cid = correlation_id or generate_correlation_id()
        bind_context(correlation_id=cid)
        return cid

    def clear_correlation(self) -> None:
        """Clear all bound context variables."""
        clear_context()
