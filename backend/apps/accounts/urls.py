from django.urls import path

from apps.accounts.face_views import (
    FaceAuthCallbackView,
    FaceAuthOptionsView,
    FaceAuthPendingView,
    FaceAuthStartView,
)
from apps.accounts.views import LoginView, MeView, RefreshView, SwitchOrganizationView

urlpatterns = [
    path("auth/token/", LoginView.as_view(), name="token-obtain"),
    path("auth/token/refresh/", RefreshView.as_view(), name="token-refresh"),
    path("auth/switch-organization/", SwitchOrganizationView.as_view(), name="switch-organization"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("auth/faceauth/options/", FaceAuthOptionsView.as_view(), name="faceauth-options"),
    path("auth/faceauth/callback/", FaceAuthCallbackView.as_view(), name="faceauth-callback"),
    path("auth/faceauth/start/", FaceAuthStartView.as_view(), name="faceauth-start"),
    path("auth/faceauth/pending/", FaceAuthPendingView.as_view(), name="faceauth-pending"),
]
