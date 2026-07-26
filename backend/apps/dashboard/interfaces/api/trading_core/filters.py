from __future__ import annotations

import django_filters
from django.db.models import Q

from apps.dashboard.infrastructure.trading_core.models import (
    OrderSnapshot,
    PositionSnapshot,
    TradeRecord,
)

VALID_ORDER_STATUSES = {"pending", "partially_filled", "filled", "cancelled", "rejected", "expired"}


class PositionFilter(django_filters.FilterSet):
    symbol = django_filters.CharFilter(lookup_expr="exact")
    side = django_filters.CharFilter(lookup_expr="exact")

    class Meta:
        model = PositionSnapshot
        fields = ["symbol", "side"]


class OrderFilter(django_filters.FilterSet):
    symbol = django_filters.CharFilter(lookup_expr="exact")
    side = django_filters.CharFilter(lookup_expr="exact")
    status = django_filters.CharFilter(method="filter_status")
    date_from = django_filters.DateTimeFilter(field_name="placed_at", lookup_expr="gte")
    date_to = django_filters.DateTimeFilter(field_name="placed_at", lookup_expr="lte")

    class Meta:
        model = OrderSnapshot
        fields = ["symbol", "side", "status", "date_from", "date_to"]

    def filter_status(self, queryset: object, name: str, value: str) -> object:
        if value not in VALID_ORDER_STATUSES:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                f"Invalid status '{value}'. Valid values: {', '.join(sorted(VALID_ORDER_STATUSES))}"
            )
        return queryset.filter(**{name: value})


class TradeFilter(django_filters.FilterSet):
    symbol = django_filters.CharFilter(lookup_expr="exact")
    side = django_filters.CharFilter(lookup_expr="exact")
    date_from = django_filters.DateTimeFilter(field_name="closed_at", lookup_expr="gte")
    date_to = django_filters.DateTimeFilter(field_name="closed_at", lookup_expr="lte")
    min_pnl = django_filters.NumberFilter(field_name="realized_pnl", lookup_expr="gte")
    max_pnl = django_filters.NumberFilter(field_name="realized_pnl", lookup_expr="lte")

    class Meta:
        model = TradeRecord
        fields = ["symbol", "side", "date_from", "date_to", "min_pnl", "max_pnl"]
