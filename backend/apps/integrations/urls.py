from django.urls import path

from apps.integrations.views import (
    FaceAuthIntegrationView,
    FaceAuthMetricsView,
    FaceAuthTestConnectionView,
)

urlpatterns = [
    path("faceauth-integration/", FaceAuthIntegrationView.as_view(), name="faceauth-integration"),
    path(
        "faceauth-integration/test/",
        FaceAuthTestConnectionView.as_view(),
        name="faceauth-integration-test",
    ),
    path(
        "faceauth-integration/metrics/",
        FaceAuthMetricsView.as_view(),
        name="faceauth-integration-metrics",
    ),
]
