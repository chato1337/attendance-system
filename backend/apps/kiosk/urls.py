from rest_framework.routers import DefaultRouter

from apps.kiosk.views import FaceEnrollmentSessionViewSet, KioskViewSet

router = DefaultRouter()
router.register("kiosks", KioskViewSet, basename="kiosk")
router.register(
    "face-enrollment-sessions",
    FaceEnrollmentSessionViewSet,
    basename="face-enrollment-session",
)

urlpatterns = router.urls
