from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.infrastructure.permissions import IsStaffRole
from apps.audit_log.infrastructure.models import AuditLogEntry
from apps.audit_log.serializers import AuditLogEntrySerializer


class AuditLogEntryListView(ListAPIView):
    permission_classes = [IsStaffRole]
    serializer_class = AuditLogEntrySerializer

    def get_queryset(self) -> object:
        qs = AuditLogEntry.objects.all().order_by("-occurred_at")
        target_type = self.request.query_params.get("target_type")
        target_id = self.request.query_params.get("target_id")

        if target_type:
            qs = qs.filter(target_type=target_type)
        if target_id:
            qs = qs.filter(target_id=target_id)

        return qs
