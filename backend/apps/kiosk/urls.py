from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.kiosk.device import (
    EnrollmentCompleteView,
    EnrollmentFailView,
    EnrollmentHostedStartView,
    KioskEmployeeLookupView,
    KioskEnrollmentStartView,
    KioskFaceIdentifyDetailView,
    KioskFaceIdentifyView,
    KioskHeartbeatView,
    KioskHostedStartView,
    KioskMeView,
)
from apps.kiosk.views import FaceEnrollmentSessionViewSet, KioskViewSet

router = DefaultRouter()
router.register("kiosks", KioskViewSet, basename="kiosk")
router.register(
    "face-enrollment-sessions",
    FaceEnrollmentSessionViewSet,
    basename="face-enrollment-session",
)

urlpatterns = [
    path("kiosk/me/", KioskMeView.as_view(), name="kiosk-me"),
    path("kiosk/heartbeat/", KioskHeartbeatView.as_view(), name="kiosk-heartbeat"),
    path("kiosk/face-identify/", KioskFaceIdentifyView.as_view(), name="kiosk-face-identify"),
    path(
        "kiosk/face-identify/<uuid:request_id>/",
        KioskFaceIdentifyDetailView.as_view(),
        name="kiosk-face-identify-detail",
    ),
    path(
        "kiosk/employees/lookup/",
        KioskEmployeeLookupView.as_view(),
        name="kiosk-employee-lookup",
    ),
    path(
        "kiosk/face-enrollment-sessions/",
        KioskEnrollmentStartView.as_view(),
        name="kiosk-face-enrollment-start",
    ),
    path("kiosk/faceauth/start/", KioskHostedStartView.as_view(), name="kiosk-faceauth-start"),
    path(
        "face-enrollment-sessions/<uuid:session_id>/complete/",
        EnrollmentCompleteView.as_view(),
        name="face-enrollment-complete",
    ),
    path(
        "face-enrollment-sessions/<uuid:session_id>/fail/",
        EnrollmentFailView.as_view(),
        name="face-enrollment-fail",
    ),
    path(
        "face-enrollment-sessions/<uuid:session_id>/hosted-start/",
        EnrollmentHostedStartView.as_view(),
        name="face-enrollment-hosted-start",
    ),
    *router.urls,
]
