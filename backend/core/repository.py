"""
TradeVision AI — Generic typed repository interface.

Defines the abstract contract for all data access layers. Concrete
repositories in ``apps/<app>/repository.py`` inherit from ``BaseRepository``
and implement each method against the Django ORM.

This file contains no ORM code, no Django imports, and no queries.
It is a pure interface definition following the Repository pattern from
Clean Architecture, which keeps business logic decoupled from persistence.

Usage::

    class MarketDataRepository(BaseRepository[MarketData]):
        def get_by_id(self, entity_id: uuid.UUID) -> MarketData | None:
            return MarketData.objects.filter(pk=entity_id).first()
        ...
"""

import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    """
    Abstract typed repository interface.

    Provides a standard set of CRUD operations plus existence and count
    queries. The generic type parameter ``T`` binds the repository to a
    specific domain entity type.

    All implementations must be independently unit-testable — the service
    layer should depend on this interface (not on concrete ORM queries) so
    that repositories can be replaced with test doubles in unit tests.

    Type parameter:
        T: The domain entity type managed by this repository.
    """

    @abstractmethod
    def get_by_id(self, entity_id: uuid.UUID) -> T | None:
        """
        Retrieve a single entity by its primary key.

        Args:
            entity_id: The UUID primary key of the entity.

        Returns:
            The entity if found, ``None`` if it does not exist.
        """

    @abstractmethod
    def list(self, **filters: Any) -> list[T]:
        """
        Retrieve all entities matching the given keyword filters.

        Args:
            **filters: Arbitrary key-value pairs passed to the underlying
                       storage layer as filter criteria.

        Returns:
            A list of matching entities (empty list if none found).
        """

    @abstractmethod
    def create(self, entity: T) -> T:
        """
        Persist a new entity and return it with any storage-assigned fields.

        Args:
            entity: The entity to persist.

        Returns:
            The persisted entity (may differ from the input if the storage
            layer populates fields such as timestamps or auto-increments).
        """

    @abstractmethod
    def update(self, entity: T) -> T:
        """
        Update an existing entity in storage and return the updated version.

        Args:
            entity: The entity with updated field values.

        Returns:
            The updated entity as reflected in storage.
        """

    @abstractmethod
    def delete(self, entity_id: uuid.UUID) -> None:
        """
        Remove an entity from storage by its primary key.

        For models that inherit ``SoftDeleteMixin``, implementations should
        perform a soft-delete rather than a physical ``DELETE`` statement.

        Args:
            entity_id: The UUID primary key of the entity to remove.
        """

    @abstractmethod
    def exists(self, entity_id: uuid.UUID) -> bool:
        """
        Return True if an entity with the given ID exists in storage.

        Args:
            entity_id: The UUID primary key to check.

        Returns:
            ``True`` if the entity exists, ``False`` otherwise.
        """

    @abstractmethod
    def count(self, **filters: Any) -> int:
        """
        Return the count of entities matching the given filters.

        Args:
            **filters: Arbitrary key-value pairs used as filter criteria.

        Returns:
            Integer count of matching entities.
        """
