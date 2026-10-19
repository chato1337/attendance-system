from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.integrations.views import (
    APITokenViewSet,
    FaceAuthIntegrationView,
    FaceAuthMetricsView,
    FaceAuthTestConnectionView,
    WebhookDeliveryViewSet,
    WebhookSubscriptionViewSet,
)

router = DefaultRouter()
router.register("webhooks", WebhookSubscriptionViewSet, basename="webhook")
router.register("webhook-deliveries", WebhookDeliveryViewSet, basename="webhook-delivery")
router.register("api-tokens", APITokenViewSet, basename="api-token")

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
    *router.urls,
]
