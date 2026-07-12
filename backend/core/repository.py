"""
TradeVision AI — Abstract base repository.

Provides ``BaseRepository[T]`` — a generic typed ABC that defines the
interface for data access layers. This is interface-only with no ORM
coupling; concrete implementations will use Django ORM or other backends.

Usage::

    class MarketDataRepository(BaseRepository[MarketData]):
        def get_by_symbol(self, symbol: str) -> MarketData | None:
            return MarketData.objects.filter(symbol=symbol).first()
"""

import abc
from typing import Any, Generic, TypeVar

from core.exceptions import TradeVisionError

T = TypeVar("T")


class BaseRepository(abc.ABC, Generic[T]):
    """
    Abstract generic repository interface.

    Subclasses must implement all methods. The type parameter ``T`` is the
    domain model this repository manages.
    """

    @abc.abstractmethod
    def get_by_id(self, id: Any) -> T | None:
        """Return a single record by its primary key, or None."""

    @abc.abstractmethod
    def create(self, **kwargs: Any) -> T:
        """Create and persist a new record."""

    @abc.abstractmethod
    def update(self, id: Any, **kwargs: Any) -> T:
        """Update an existing record. Raises TradeVisionError if not found."""

    @abc.abstractmethod
    def delete(self, id: Any) -> bool:
        """Soft-delete a record. Returns True if deleted."""

    @abc.abstractmethod
    def list_all(self, **filters: Any) -> list[T]:
        """Return all records matching the given filters."""
