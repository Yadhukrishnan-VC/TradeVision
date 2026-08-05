"""BacktestRun persistence — plain CRUD over the ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from core.repository import BaseRepository

from apps.backtesting.models import BacktestRun, BacktestRunStatus


class BacktestRunRepository(BaseRepository[BacktestRun]):
    def get_by_id(self, entity_id: uuid.UUID) -> BacktestRun | None:
        try:
            return BacktestRun.objects.get(id=entity_id)
        except BacktestRun.DoesNotExist:
            return None

    def list(self, **filters: Any) -> list[BacktestRun]:
        return list(BacktestRun.objects.filter(**filters).order_by("-created_at"))

    def create(self, entity: BacktestRun) -> BacktestRun:
        entity.full_clean()
        entity.save()
        return entity

    def update(self, entity: BacktestRun) -> BacktestRun:
        entity.full_clean()
        entity.save()
        return entity

    def delete(self, entity_id: uuid.UUID) -> None:
        BacktestRun.all_objects.filter(id=entity_id).hard_delete()

    def exists(self, entity_id: uuid.UUID) -> bool:
        return BacktestRun.objects.filter(id=entity_id).exists()

    def count(self, **filters: Any) -> int:
        return BacktestRun.objects.filter(**filters).count()

    # ------------------------------------------------------------------
    # Lifecycle transitions
    # ------------------------------------------------------------------

    def mark_running(self, run_id: uuid.UUID, started_at: datetime | None = None) -> None:
        BacktestRun.objects.filter(id=run_id).update(
            status=BacktestRunStatus.RUNNING,
            started_at=started_at,
        )

    def mark_completed(self, run_id: uuid.UUID, completed_at: datetime | None = None) -> None:
        BacktestRun.objects.filter(id=run_id).update(
            status=BacktestRunStatus.COMPLETED,
            completed_at=completed_at,
        )

    def mark_failed(self, run_id: uuid.UUID, reason: str) -> None:
        BacktestRun.objects.filter(id=run_id).update(
            status=BacktestRunStatus.FAILED,
            failure_reason=reason[:4000] if reason else "",
        )

    def update_cursor(self, run_id: uuid.UUID, snapshot_id: uuid.UUID) -> None:
        BacktestRun.objects.filter(id=run_id).update(
            last_processed_snapshot_id=snapshot_id,
        )
