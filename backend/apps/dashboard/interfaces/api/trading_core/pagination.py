from __future__ import annotations

from rest_framework.pagination import CursorPagination


class DashboardCursorPagination(CursorPagination):
    page_size = 20
    ordering = "-placed_at"

    def paginate_queryset(self, queryset: object, request: object, view: object = None) -> object:
        return super().paginate_queryset(queryset, request, view)  # type: ignore[misc]


class PositionCursorPagination(CursorPagination):
    page_size = 20
    ordering = "-opened_at"


class OrderCursorPagination(CursorPagination):
    page_size = 20
    ordering = "-placed_at"


class TradeCursorPagination(CursorPagination):
    page_size = 20
    ordering = "-closed_at"
