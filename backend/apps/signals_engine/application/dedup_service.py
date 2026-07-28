from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.services import BaseService
from apps.signals_engine.infrastructure.models import Signal


class DedupService(BaseService):
    def is_duplicate(self, source_alert_id: str) -> bool:
        window_seconds = getattr(settings, "SIGNAL_DEDUP_WINDOW_SECONDS", 300)
        cutoff = timezone.now() - timedelta(seconds=window_seconds)
        with transaction.atomic():
            rows = list(
                Signal.objects.select_for_update().filter(
                    source_alert_id=source_alert_id,
                    created_at__gte=cutoff,
                )[:1]
            )
            return len(rows) > 0
