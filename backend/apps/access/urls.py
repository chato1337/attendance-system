from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.access.views import (
    AccessAnomalyViewSet,
    AccessLogViewSet,
    AccessNodeViewSet,
    DoorViewSet,
    OccupancyResetView,
    OccupancyView,
    ReaderProfileViewSet,
    ReaderViewSet,
    ZoneViewSet,
)

router = DefaultRouter()
router.register("zones", ZoneViewSet, basename="zone")
router.register("reader-profiles", ReaderProfileViewSet, basename="reader-profile")
router.register("nodes", AccessNodeViewSet, basename="node")
router.register("doors", DoorViewSet, basename="door")
router.register("readers", ReaderViewSet, basename="reader")
router.register("access-logs", AccessLogViewSet, basename="access-log")
router.register("access-anomalies", AccessAnomalyViewSet, basename="access-anomaly")

urlpatterns = [
    path("occupancy/", OccupancyView.as_view(), name="occupancy"),
    path("occupancy/reset/", OccupancyResetView.as_view(), name="occupancy-reset"),
    *router.urls,
]
