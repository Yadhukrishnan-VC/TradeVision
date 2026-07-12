"""
TradeVision AI — Structural Protocol classes.

Defines ``typing.Protocol`` classes that capture the structural contracts
expected by the repository and service layers. These are not base classes
to inherit from — they describe the shape that concrete classes must satisfy.

Usage::

    from core.protocols import Identifiable, SoftDeletable

    def delete_record(obj: SoftDeletable) -> None:
        obj.soft_delete()
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Identifiable(Protocol):
    """Structural protocol for objects with a primary key."""

    @property
    def pk(self) -> object: ...


@runtime_checkable
class Timestamped(Protocol):
    """Structural protocol for objects with creation and update timestamps."""

    @property
    def created_at(self) -> object: ...

    @property
    def updated_at(self) -> object: ...


@runtime_checkable
class SoftDeletable(Protocol):
    """Structural protocol for objects that support soft-deletion."""

    is_deleted: bool

    def delete(self) -> None: ...

    def restore(self) -> None: ...


@runtime_checkable
class Auditable(Protocol):
    """Structural protocol for objects that track who created/updated them."""

    created_by: object
    updated_by: object
