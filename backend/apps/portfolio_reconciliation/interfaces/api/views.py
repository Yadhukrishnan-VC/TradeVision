"""PORTFOLIO-RECONCILE-1 — API views.

Read-only operator endpoints exposing the append-only drift log produced by
the reconciliation engine:

- ``GET /api/v1/portfolio-reconciliation/drift/`` — paginated
  ``DriftRecord`` listing, filterable by ``account_id``,
  ``classification`` and ``auto_repaired``.
- ``GET /api/v1/portfolio-reconciliation/drift/summary/`` — counts by
  classification and the most recent detection timestamp.

Both require an authenticated OWNER or STAFF account (the same
``IsStaffRole`` gate used by ``apps.audit_log``), and only ever read the
``DriftRecord`` log — no reconciliation state can be mutated through the
API.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db.models import Count, Max
from rest_framework import serializers as drf_serializers
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.infrastructure.permissions import IsStaffRole
from apps.portfolio_reconciliation.infrastructure.models import DriftRecord
from apps.portfolio_reconciliation.interfaces.api.serializers import (
    DriftRecordSerializer,
    DriftSummarySerializer,
)
from core.pagination import StandardResultsPagination

_CLASSIFICATION_VALUES = (
    "MATCHED",
    "MISSING_IN_READ_MODEL",
    "STALE_IN_READ_MODEL",
    "ORPHANED_IN_READ_MODEL",
    "COMPARISON_ERROR",
)


class DriftRecordListView(ListAPIView):
    """GET /drift/ — paginated drift detection log (OWNER/STAFF only)."""

    permission_classes = [IsStaffRole]
    serializer_class = DriftRecordSerializer
    pagination_class = StandardResultsPagination

    def get_queryset(self) -> object:
        qs = DriftRecord.objects.all().order_by("-detected_at")
        params = self.request.query_params

        account_id = params.get("account_id")
        if account_id:
            try:
                qs = qs.filter(account_id=uuid.UUID(account_id))
            except ValueError:
                raise drf_serializers.ValidationError(
                    {"account_id": "Must be a valid UUID."}
                )

        classification = params.get("classification")
        if classification:
            if classification not in _CLASSIFICATION_VALUES:
                raise drf_serializers.ValidationError(
                    {
                        "classification": (
                            "Must be one of: "
                            + ", ".join(_CLASSIFICATION_VALUES)
                            + "."
                        )
                    }
                )
            qs = qs.filter(classification=classification)

        auto_repaired = params.get("auto_repaired")
        if auto_repaired is not None:
            lowered = auto_repaired.strip().lower()
            if lowered not in ("true", "false"):
                raise drf_serializers.ValidationError(
                    {"auto_repaired": "Must be 'true' or 'false'."}
                )
            qs = qs.filter(auto_repaired=(lowered == "true"))

        return qs


class DriftSummaryView(GenericAPIView):
    """GET /drift/summary/ — per-classification counts + last run time."""

    permission_classes = [IsStaffRole]
    serializer_class = DriftSummarySerializer

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        qs = DriftRecord.objects.all()
        account_id = request.query_params.get("account_id")
        if account_id:
            try:
                qs = qs.filter(account_id=uuid.UUID(account_id))
            except ValueError:
                raise drf_serializers.ValidationError(
                    {"account_id": "Must be a valid UUID."}
                )

        breakdown: dict[str, int] = {
            row["classification"]: row["count"]
            for row in qs.values("classification").annotate(count=Count("id"))
        }
        last_run = qs.aggregate(latest=Max("detected_at"))["latest"]
        data = {
            "classification_breakdown": breakdown,
            "total_records": sum(breakdown.values()),
            "last_run_at": last_run,
        }
        serializer = self.get_serializer(data)
        return Response(serializer.data)