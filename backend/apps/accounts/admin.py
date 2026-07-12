"""
TradeVision AI — Accounts admin configuration.

Registers the custom ``User`` model with a tailored ``UserAdmin`` that:
- Uses email instead of username in all list/search views
- Groups fields logically (credentials, role, permissions, metadata)
- Marks audit fields as read-only
- Disables hard-deletion (soft-delete is not used on User, but hard
  deletion is still disabled in the admin to prevent accidental data loss)
"""

import logging

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.http import HttpRequest

from apps.common.admin import BaseModelAdmin

from .models import User

logger = logging.getLogger(__name__)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """
    Admin configuration for the custom ``User`` model.

    Extends Django's built-in ``UserAdmin`` to accommodate the email-only
    authentication scheme and UUID primary key.
    """

    list_display = ("email", "role", "is_active", "is_staff", "created_at")
    list_filter = ("role", "is_active", "is_staff", "is_superuser")
    search_fields = ("email",)
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "updated_at", "last_login")

    # Field layout for the edit form
    fieldsets = (
        (
            "Credentials",
            {"fields": ("email", "password")},
        ),
        (
            "Role",
            {"fields": ("role",)},
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("id", "created_at", "updated_at", "last_login"),
                "classes": ("collapse",),
            },
        ),
    )

    # Field layout for the "add user" form
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "role"),
            },
        ),
    )

    # DjangoUserAdmin sets ordering based on username — override for email
    ordering = ("-created_at",)  # type: ignore[assignment]

    # Required by DjangoUserAdmin — maps to our email-based model
    filter_horizontal = ("groups", "user_permissions")

    def has_delete_permission(
        self, request: HttpRequest, obj: object = None
    ) -> bool:
        """
        Disable hard-deletion of user accounts from the admin.

        User accounts should be deactivated (``is_active=False``) rather
        than deleted to preserve foreign key references and audit history.
        """
        return False
