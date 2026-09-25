from django.urls import path

from apps.eventbus.interfaces.api.views import ActivityFeedView

app_name = "eventbus"

urlpatterns = [
    path("activity/", ActivityFeedView.as_view(), name="activity-feed"),
]