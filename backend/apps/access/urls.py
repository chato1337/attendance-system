from rest_framework.routers import DefaultRouter

from apps.access.views import (
    AccessLogViewSet,
    AccessNodeViewSet,
    DoorViewSet,
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

urlpatterns = router.urls
