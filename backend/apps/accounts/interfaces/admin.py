from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.infrastructure.models import APIKey, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin configuration for the custom User model."""

    list_display = ("username", "email", "role", "is_staff", "is_active", "date_joined")
    list_filter = ("role", "is_staff", "is_superuser", "is_active")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email")}),
        ("Permissions", {"fields": ("role", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    """Admin configuration for API keys."""

    list_display = ("id", "user", "scopes", "revoked_at", "created_at")
    list_filter = ("revoked_at", "created_at")
    search_fields = ("user__username",)
    readonly_fields = ("id", "key_hash", "created_at", "updated_at")
