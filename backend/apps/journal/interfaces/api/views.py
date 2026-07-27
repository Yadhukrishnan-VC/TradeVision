from __future__ import annotations

import uuid
from typing import Any

from rest_framework import status
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.journal.application.journal_query_service import JournalQueryService
from apps.journal.domain.exceptions import JournalEntryNotFound
from apps.journal.interfaces.api.serializers import JournalEntrySerializer


def _problem_detail(
    exc_type: str, title: str, status_code: int, instance: str, correlation_id: str
) -> dict[str, Any]:
    return {
        "type": f"urn:tradevision:error:{exc_type}",
        "title": title,
        "status": status_code,
        "instance": instance,
        "correlation_id": correlation_id,
    }


class JournalEntryDetailView(GenericAPIView):
    serializer_class = JournalEntrySerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = JournalQueryService()

    def get(self, request: Request, correlation_id: str, *args: Any, **kwargs: Any) -> Response:
        try:
            snapshot = self._service.get_entry(uuid.UUID(correlation_id))
        except JournalEntryNotFound:
            return Response(
                _problem_detail(
                    "journal-entry-not-found",
                    f"Journal entry {correlation_id} not found",
                    status.HTTP_404_NOT_FOUND,
                    request.path,
                    str(getattr(request, "correlation_id", "")),
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(snapshot)
        return Response(serializer.data)


class JournalEntryListView(ListAPIView):
    serializer_class = JournalEntrySerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = JournalQueryService()

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        account_id = request.query_params.get("account_id")
        if not account_id:
            return Response(
                {"error": {"code": "missing_account_id", "message": "account_id query parameter is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        finalized_param = request.query_params.get("finalized")
        finalized: bool | None = None
        if finalized_param is not None:
            finalized = finalized_param.lower() in ("true", "1", "yes")

        snapshots = self._service.get_entries(
            account_id=uuid.UUID(account_id),
            finalized=finalized,
        )
        serializer = self.get_serializer(snapshots, many=True)
        return Response(serializer.data)
