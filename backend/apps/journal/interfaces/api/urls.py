from __future__ import annotations

from django.urls import path

from apps.journal.interfaces.api.views import JournalEntryDetailView, JournalEntryListView

urlpatterns = [
    path("entries/", JournalEntryListView.as_view(), name="journal-entry-list"),
    path("entries/<uuid:correlation_id>/", JournalEntryDetailView.as_view(), name="journal-entry-detail"),
]
