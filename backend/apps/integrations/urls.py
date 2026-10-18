from django.urls import path

from apps.integrations.views import FaceAuthIntegrationView

urlpatterns = [
    path("faceauth-integration/", FaceAuthIntegrationView.as_view(), name="faceauth-integration"),
]
