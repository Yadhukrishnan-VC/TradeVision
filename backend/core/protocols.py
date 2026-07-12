"""
TradeVision AI — Structural protocols for domain entity contracts.

Python ``Protocol`` classes define structural interfaces without requiring
inheritance. They complement the abstract base classes in ``core.models``
by providing type-safe contracts that can be checked with ``isinstance()``
at runtime (via ``@runtime_checkable``).

These protocols are used in type annotations across service and repository
layers to express constraints without coupling to concrete Django model
classes.

Usage::

    from core.protocols import Identifiable, SoftDeletable

    def archive(entity: SoftDeletable) -> None:
        entity.delete()
"""

import uuid
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Identifiable(Protocol):
    """
    Protocol for entities that carry a UUID primary key.

    Satisfied by any object with an ``id`` attribute of type ``uuid.UUID``.
    All models that inherit from ``UUIDMixin`` automatically satisfy this.
    """

    id: uuid.UUID


@runtime_checkable
class Timestamped(Protocol):
    """
    Protocol for entities that track creation and modification times.

    Satisfied by any object with ``created_at`` and ``updated_at`` attributes
    of type ``datetime``. All models that inherit from ``TimestampMixin``
    automatically satisfy this.
    """

    created_at: datetime
    updated_at: datetime


@runtime_checkable
class SoftDeletable(Protocol):
    """
    Protocol for entities that support soft-deletion semantics.

    Satisfied by any object that exposes ``is_deleted``, ``deleted_at``,
    a ``delete()`` method, and a ``restore()`` method. All models that
    inherit from ``SoftDeleteMixin`` automatically satisfy this.
    """

    is_deleted: bool
    deleted_at: datetime | None

    def delete(self) -> None:
        """Soft-delete this entity."""
        ...

    def restore(self) -> None:
        """Restore a previously soft-deleted entity."""
        ...


@runtime_checkable
class Auditable(Protocol):
    """
    Protocol for entities that track which user created or modified them.

    Satisfied by any object with ``created_by`` and ``updated_by`` attributes.
    All models that inherit from ``AuditMixin`` automatically satisfy this.
    The attribute type is ``Any`` because the User model varies by project.
    """

    created_by: Any
    updated_by: Any
