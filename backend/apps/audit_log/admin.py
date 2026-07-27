from __future__ import annotations

from django.contrib import admin

from apps.audit_log.infrastructure.models import AuditLogEntry


@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "actor", "action", "target_type", "target_id", "occurred_at")
    list_filter = ("actor", "action", "occurred_at")
    search_fields = ("target_type", "target_id", "action")
    readonly_fields = ("id", "actor", "action", "target_type", "target_id", "metadata", "occurred_at", "created_at", "updated_at")

    def has_add_permission(self, request, view=None) -> bool:
        return False

    def has_change_permission(self, request, view=None) -> bool:
        return False

    def has_delete_permission(self, request, view=None) -> bool:
        return False
