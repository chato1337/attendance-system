from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.reports.views import (
    AttendanceViewSet,
    ExportDownloadView,
    ExportJobViewSet,
    HolidayViewSet,
    RecalculateView,
    ScheduleViewSet,
    ShiftViewSet,
    SummaryView,
)

router = DefaultRouter()
router.register("shifts", ShiftViewSet, basename="shift")
router.register("schedules", ScheduleViewSet, basename="schedule")
router.register("holidays", HolidayViewSet, basename="holiday")
router.register("reports/attendance", AttendanceViewSet, basename="attendance")
router.register("reports/exports", ExportJobViewSet, basename="report-export")

urlpatterns = [
    path("reports/summary/", SummaryView.as_view(), name="report-summary"),
    path("reports/recalculate/", RecalculateView.as_view(), name="report-recalculate"),
    path(
        "reports/exports/<uuid:pk>/download/",
        ExportDownloadView.as_view(),
        name="report-export-download",
    ),
    *router.urls,
]
