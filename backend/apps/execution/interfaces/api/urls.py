from __future__ import annotations

from django.urls import path

from apps.execution.interfaces.api.views import (
    ExecutionRequestListView,
    OrderDetailView,
    OrderListView,
)

urlpatterns = [
    path("requests/", ExecutionRequestListView.as_view(), name="execution-request-list"),
    path("orders/", OrderListView.as_view(), name="execution-order-list"),
    path("orders/<uuid:pk>/", OrderDetailView.as_view(), name="execution-order-detail"),
]
