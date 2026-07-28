from __future__ import annotations

from django.urls import path

from apps.recommendations.interfaces.api.views import (
    RecommendationAcceptView,
    RecommendationDetailView,
    RecommendationExplanationView,
    RecommendationListView,
    RecommendationRejectView,
)

urlpatterns = [
    path("", RecommendationListView.as_view(), name="recommendation-list"),
    path("<uuid:pk>/", RecommendationDetailView.as_view(), name="recommendation-detail"),
    path("<uuid:pk>/accept/", RecommendationAcceptView.as_view(), name="recommendation-accept"),
    path("<uuid:pk>/reject/", RecommendationRejectView.as_view(), name="recommendation-reject"),
    path("<uuid:pk>/explanation/", RecommendationExplanationView.as_view(), name="recommendation-explanation"),
]
