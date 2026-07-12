"""
TradeVision AI — Django admin base configuration.

Provides a customised admin site and a base ``ModelAdmin`` class that all
app-level admins should inherit from. Enforces consistent behaviour:
- Audit fields are always read-only
- Hard deletion is disabled (soft-delete only)
- Page size is standardised
"""

import logging

from django.contrib import admin
from django.contrib.admin import ModelAdmin
from django.db.models import QuerySet
from django.http import HttpRequest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Admin site customisation
# ---------------------------------------------------------------------------

admin.site.site_title = "TradeVision AI"
admin.site.site_header = "TradeVision AI — Administration"
admin.site.index_title = "Platform Dashboard"


# ---------------------------------------------------------------------------
# Base ModelAdmin
# ---------------------------------------------------------------------------


class BaseModelAdmin(ModelAdmin):
    """
    Base class for all TradeVision AI ``ModelAdmin`` registrations.

    Enforces:
    - UUID, timestamps, and soft-delete fields are read-only in every form.
    - Hard-delete is disabled — only soft-delete is permitted through the UI.
    - Standard list page size of 25 rows.
    - Provides a ``restore_selected`` action for soft-deleted records.

    Every app admin should extend this class::

        @admin.register(MarketData)
        class MarketDataAdmin(BaseModelAdmin):
            list_display = ("symbol", "timestamp", "close_price")
    """

    list_per_page: int = 25
    readonly_fields: tuple[str, ...] = (
        "id",
        "created_at",
        "updated_at",
        "is_deleted",
        "deleted_at",
    )

    def has_delete_permission(
        self, request: HttpRequest, obj: object = None
    ) -> bool:
        """
        Disable hard-delete in the admin.

        Deletion is handled via the ``soft_delete_selected`` action, which
        calls the model's ``delete()`` method (soft-delete).
        """
        return False

    @admin.action(description="Soft-delete selected records")
    def soft_delete_selected(
        self,
        request: HttpRequest,
        queryset: QuerySet,
    ) -> None:
        """
        Soft-delete all selected records by calling the model's delete() method.

        Invokes per-instance ``delete()`` (rather than bulk SQL) to ensure
        the model's soft-delete logic and logging run for every record.
        """
        count = 0
        for obj in queryset:
            obj.delete()
            count += 1
        self.message_user(request, f"{count} record(s) soft-deleted.")
        logger.info(
            "admin_soft_delete",
            extra={"count": count, "model": queryset.model.__name__},
        )

    @admin.action(description="Restore selected soft-deleted records")
    def restore_selected(
        self,
        request: HttpRequest,
        queryset: QuerySet,
    ) -> None:
        """
        Restore all soft-deleted records in the queryset.

        Only meaningful when the admin list view uses ``all_objects``
        instead of the default ``objects`` manager.
        """
        count = queryset.restore() if hasattr(queryset, "restore") else 0
        self.message_user(request, f"{count} record(s) restored.")
        logger.info(
            "admin_restore",
            extra={"count": count, "model": queryset.model.__name__},
        )

    actions = [soft_delete_selected, restore_selected]


# ---------------------------------------------------------------------------
# SoftDeleteAdmin — shows all records (including deleted) in the admin
# ---------------------------------------------------------------------------


class SoftDeleteAdmin(BaseModelAdmin):
    """
    ModelAdmin variant that exposes soft-deleted records.

    Uses ``all_objects`` as the default queryset so admins can review
    and restore deleted records.

    Adds a visual indicator to the list display for deleted records.
    """

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        """Return all records including soft-deleted ones."""
        qs = self.model.all_objects.all()
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        return qs
