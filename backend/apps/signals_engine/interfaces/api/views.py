from __future__ import annotations

import uuid

from rest_framework import generics, permissions

from apps.signals_engine.infrastructure.models import Signal
from apps.signals_engine.interfaces.api.serializers import SignalSerializer


class SignalListCreateView(generics.ListAPIView):
    """Paginated list of recent Signal records.

    Read-only — signals are created exclusively via the
    ``signals.SignalCreated`` event-driven path from
    ``ingestion.RawAlertReceived``.
    """

    queryset = Signal.objects.all().order_by("-created_at")
    serializer_class = SignalSerializer
    permission_classes = (permissions.IsAuthenticated,)


class SignalDetailView(generics.RetrieveAPIView):
    """Single Signal detail, including indicator_snapshot."""

    queryset = Signal.objects.all()
    serializer_class = SignalSerializer
    permission_classes = (permissions.IsAuthenticated,)
