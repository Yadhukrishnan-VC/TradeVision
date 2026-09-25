from __future__ import annotations

from typing import Any

from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.eventbus.infrastructure.models import StoredEvent


class ActivityFeedView(GenericAPIView):
    """Realtime activity feed: most recent published domain events.

    Read directly from the append-only ``StoredEvent`` store so consumers see
    the same sequence the eventbus streams expose. Supports ``?limit`` (cap
    100), ``?event_type=`` filtering, and ``?since=<iso-datetime>`` for
    incremental polling.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        try:
            limit = min(max(int(request.query_params.get("limit", 50)), 1), 100)
        except (TypeError, ValueError):
            limit = 50

        qs = StoredEvent.objects.all().order_by("-occurred_at")

        event_type = request.query_params.get("event_type")
        if event_type:
            qs = qs.filter(event_type=event_type)

        since = request.query_params.get("since")
        if since:
            from django.utils.timezone import make_aware
            from datetime import datetime

            try:
                since_dt = datetime.fromisoformat(since)
                if since_dt.tzinfo is None:
                    since_dt = make_aware(since_dt)
                qs = qs.filter(occurred_at__gt=since_dt)
            except ValueError:
                qs = qs.filter(pk__isnull=False)

        events = qs[:limit]
        return Response(
            {
                "events": [
                    {
                        "event_id": str(e.event_id),
                        "event_type": e.event_type,
                        "occurred_at": e.occurred_at.isoformat(),
                        "version": e.version,
                        "payload": e.payload,
                        "correlation_id": str(e.correlation_id),
                    }
                    for e in events
                ]
            }
        )