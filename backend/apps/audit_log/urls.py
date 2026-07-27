from __future__ import annotations

from django.urls import path

from apps.audit_log.views import AuditLogEntryListView

urlpatterns = [
    path("entries/", AuditLogEntryListView.as_view(), name="audit-log-entry-list"),
]
