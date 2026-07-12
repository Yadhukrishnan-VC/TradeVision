"""
TradeVision AI — Abstract base models and reusable model mixins.

All domain models must inherit from ``BaseModel``. Individual mixins are
available for cases where the full contract is not needed (e.g. a through
model that does not require soft-deletion).

Dependency rule: this module must never import from any ``apps.*`` module
to avoid circular imports. The ``AuditMixin`` uses ``settings.AUTH_USER_MODEL``
(a string), which Django resolves lazily at migration time.
"""

import logging
import uuid
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# UUIDMixin
# ---------------------------------------------------------------------------


class UUIDMixin(models.Model):
    """
    Replaces the default auto-increment integer primary key with a UUID4.

    UUID keys are:
    - Non-guessable (unlike sequential integers)
    - Portable across database instances and environments
    - Consistent with REST resource identifiers in the API layer
    """

    id: models.UUIDField = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier (UUID4, not auto-increment).",
    )

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# TimestampMixin
# ---------------------------------------------------------------------------


class TimestampMixin(models.Model):
    """
    Adds timezone-aware ``created_at`` and ``updated_at`` timestamps.

    Both fields are stored in UTC (``USE_TZ = True`` is enforced in settings).
    """

    created_at: models.DateTimeField = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="UTC datetime when this record was created.",
    )
    updated_at: models.DateTimeField = models.DateTimeField(
        auto_now=True,
        help_text="UTC datetime when this record was last modified.",
    )

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Soft-delete infrastructure
# ---------------------------------------------------------------------------


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet that understands soft-deletion semantics."""

    def alive(self) -> "SoftDeleteQuerySet":
        """Return only records that have not been soft-deleted."""
        return self.filter(is_deleted=False)

    def deleted(self) -> "SoftDeleteQuerySet":
        """Return only soft-deleted records."""
        return self.filter(is_deleted=True)

    def restore(self) -> int:
        """Un-delete all records in this queryset. Returns the update count."""
        return self.update(is_deleted=False, deleted_at=None)

    def delete(self) -> tuple[int, dict[str, int]]:
        """
        Soft-delete all records in this queryset.

        Returns a ``(count, {label: count})`` tuple for interface
        consistency with Django's standard ``QuerySet.delete()``.
        """
        count = self.update(is_deleted=True, deleted_at=timezone.now())
        label = f"{self.model._meta.label}"
        return count, {label: count}

    def hard_delete(self) -> tuple[int, dict[str, int]]:
        """Permanently remove all records in this queryset from the database."""
        return super().delete()


class SoftDeleteManager(models.Manager):
    """
    Default manager that excludes soft-deleted records.

    ``Model.objects.all()`` will never return records with ``is_deleted=True``.
    Use ``Model.all_objects.all()`` to include them.
    """

    def get_queryset(self) -> SoftDeleteQuerySet:
        """Return only alive (non-deleted) records."""
        return SoftDeleteQuerySet(self.model, using=self._db).alive()


class AllObjectsManager(models.Manager):
    """Manager that returns every record including soft-deleted ones."""

    def get_queryset(self) -> SoftDeleteQuerySet:
        """Return all records regardless of soft-deletion status."""
        return SoftDeleteQuerySet(self.model, using=self._db)


# ---------------------------------------------------------------------------
# SoftDeleteMixin
# ---------------------------------------------------------------------------


class SoftDeleteMixin(models.Model):
    """
    Adds soft-deletion semantics to a model.

    Instead of removing rows, sets ``is_deleted = True`` and records
    ``deleted_at``. The default ``objects`` manager filters these out;
    ``all_objects`` includes them for admin and audit use cases.
    """

    is_deleted: models.BooleanField = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True when this record has been soft-deleted.",
    )
    deleted_at: models.DateTimeField = models.DateTimeField(
        null=True,
        blank=True,
        help_text="UTC datetime when this record was soft-deleted.",
    )

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def delete(  # type: ignore[override]
        self,
        using: str | None = None,
        keep_parents: bool = False,
    ) -> None:
        """
        Soft-delete this record.

        Sets ``is_deleted=True`` and ``deleted_at`` to the current UTC time.
        The record remains in the database and is accessible via
        ``all_objects``.
        """
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at"])
        logger.debug(
            "record_soft_deleted",
            extra={"model": self.__class__.__name__, "pk": str(self.pk)},
        )

    def hard_delete(self, using: str | None = None) -> None:
        """
        Permanently remove this record from the database.

        Use only when required for compliance (e.g. GDPR erasure requests).
        Prefer ``delete()`` for normal application flows.
        """
        super().delete(using=using)  # type: ignore[call-arg]
        logger.info(
            "record_hard_deleted",
            extra={"model": self.__class__.__name__, "pk": str(self.pk)},
        )

    def restore(self) -> None:
        """Undo a soft-deletion, making this record visible to the default manager."""
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at"])
        logger.debug(
            "record_restored",
            extra={"model": self.__class__.__name__, "pk": str(self.pk)},
        )


# ---------------------------------------------------------------------------
# AuditMixin
# ---------------------------------------------------------------------------


class AuditMixin(models.Model):
    """
    Adds nullable ``created_by`` and ``updated_by`` foreign keys.

    References ``settings.AUTH_USER_MODEL`` so this mixin is not coupled
    to the concrete ``accounts.User`` app label.

    Views and services are responsible for populating these fields; they
    are not set automatically to avoid hidden coupling to the request context.
    """

    created_by: models.ForeignKey = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_created",
        help_text="User who created this record.",
    )
    updated_by: models.ForeignKey = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_updated",
        help_text="User who last updated this record.",
    )

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# BaseModel — compose everything together
# ---------------------------------------------------------------------------


class BaseModel(UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """
    Abstract base model for all TradeVision AI domain entities.

    Provides out of the box:
    - **UUID4 primary key** — non-guessable, portable, API-safe
    - **Timezone-aware timestamps** — ``created_at``, ``updated_at`` (UTC)
    - **Soft-deletion** — ``objects`` manager never returns deleted records;
      ``all_objects`` manager returns everything; ``restore()`` undoes deletion
    - **Standard ordering** — newest-first (``-created_at``)

    Usage::

        class MarketData(BaseModel):
            symbol = models.CharField(max_length=20)
            # ... additional fields

    Do NOT add ``AuditMixin`` to BaseModel — not every model needs user
    tracking, and it would create a mandatory FK to ``accounts.User`` on
    every table, complicating initial migrations.
    """

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """Return a default string representation using the class name and PK."""
        return f"{self.__class__.__name__}({self.pk})"

    def __repr__(self) -> str:
        """Return an unambiguous developer representation."""
        return f"<{self.__class__.__name__} pk={self.pk}>"
