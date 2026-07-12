"""
Tests for BaseModel, mixins, and soft-delete semantics.

``BaseModel`` is abstract, so these tests verify its metadata contracts
without requiring a concrete database table. Integration-level soft-delete
tests against a real table are co-located with the first concrete model
that uses ``BaseModel`` (added in Phase 1).
"""

import uuid

import pytest

from core.models import (
    AuditMixin,
    BaseModel,
    SoftDeleteMixin,
    SoftDeleteQuerySet,
    TimestampMixin,
    UUIDMixin,
)


# ---------------------------------------------------------------------------
# Mixin metadata contracts
# ---------------------------------------------------------------------------


class TestUUIDMixin:
    """UUIDMixin declares the correct primary key field."""

    def test_is_abstract(self) -> None:
        """UUIDMixin must be abstract — it cannot be instantiated directly."""
        assert UUIDMixin._meta.abstract is True

    def test_pk_field_is_uuid(self) -> None:
        """The ``id`` field must be a UUIDField."""
        from django.db import models

        field = UUIDMixin._meta.get_field("id")
        assert isinstance(field, models.UUIDField)

    def test_pk_default_is_uuid4(self) -> None:
        """The default callable must produce a valid UUID4."""
        field = UUIDMixin._meta.get_field("id")
        generated = field.default()
        assert isinstance(generated, uuid.UUID)
        # UUID4 variant bits — version == 4
        assert generated.version == 4

    def test_pk_not_editable(self) -> None:
        """The UUID field must not be editable."""
        field = UUIDMixin._meta.get_field("id")
        assert field.editable is False


class TestTimestampMixin:
    """TimestampMixin declares auto-managed timestamp fields."""

    def test_is_abstract(self) -> None:
        """TimestampMixin must be abstract."""
        assert TimestampMixin._meta.abstract is True

    def test_has_created_at(self) -> None:
        """``created_at`` must be a DateTimeField with auto_now_add."""
        from django.db import models

        field = TimestampMixin._meta.get_field("created_at")
        assert isinstance(field, models.DateTimeField)
        assert field.auto_now_add is True

    def test_has_updated_at(self) -> None:
        """``updated_at`` must be a DateTimeField with auto_now."""
        from django.db import models

        field = TimestampMixin._meta.get_field("updated_at")
        assert isinstance(field, models.DateTimeField)
        assert field.auto_now is True

    def test_created_at_is_indexed(self) -> None:
        """``created_at`` must carry a database index for range queries."""
        field = TimestampMixin._meta.get_field("created_at")
        assert field.db_index is True


class TestSoftDeleteMixin:
    """SoftDeleteMixin adds is_deleted and deleted_at fields."""

    def test_is_abstract(self) -> None:
        assert SoftDeleteMixin._meta.abstract is True

    def test_has_is_deleted(self) -> None:
        from django.db import models

        field = SoftDeleteMixin._meta.get_field("is_deleted")
        assert isinstance(field, models.BooleanField)
        assert field.default is False

    def test_has_deleted_at(self) -> None:
        from django.db import models

        field = SoftDeleteMixin._meta.get_field("deleted_at")
        assert isinstance(field, models.DateTimeField)
        assert field.null is True

    def test_is_deleted_is_indexed(self) -> None:
        field = SoftDeleteMixin._meta.get_field("is_deleted")
        assert field.db_index is True


class TestAuditMixin:
    """AuditMixin declares created_by and updated_by FK fields."""

    def test_is_abstract(self) -> None:
        assert AuditMixin._meta.abstract is True

    def test_has_created_by(self) -> None:
        from django.db import models

        field = AuditMixin._meta.get_field("created_by")
        assert isinstance(field, models.ForeignKey)
        assert field.null is True
        assert field.blank is True

    def test_has_updated_by(self) -> None:
        from django.db import models

        field = AuditMixin._meta.get_field("updated_by")
        assert isinstance(field, models.ForeignKey)
        assert field.null is True


# ---------------------------------------------------------------------------
# BaseModel composition
# ---------------------------------------------------------------------------


class TestBaseModel:
    """BaseModel composes UUIDMixin, TimestampMixin, and SoftDeleteMixin."""

    def test_is_abstract(self) -> None:
        """BaseModel must be abstract — only concrete subclasses have tables."""
        assert BaseModel._meta.abstract is True

    def test_default_ordering(self) -> None:
        """Default ordering must be newest-first."""
        assert BaseModel._meta.ordering == ["-created_at"]

    def test_inherits_uuid_field(self) -> None:
        """BaseModel must expose the UUID primary key from UUIDMixin."""
        field = BaseModel._meta.get_field("id")
        from django.db import models

        assert isinstance(field, models.UUIDField)

    def test_inherits_timestamp_fields(self) -> None:
        """BaseModel must expose created_at and updated_at."""
        BaseModel._meta.get_field("created_at")
        BaseModel._meta.get_field("updated_at")

    def test_inherits_soft_delete_fields(self) -> None:
        """BaseModel must expose is_deleted and deleted_at."""
        BaseModel._meta.get_field("is_deleted")
        BaseModel._meta.get_field("deleted_at")
