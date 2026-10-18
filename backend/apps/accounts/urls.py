from django.urls import path

from apps.accounts.views import LoginView, MeView, RefreshView, SwitchOrganizationView

urlpatterns = [
    path("auth/token/", LoginView.as_view(), name="token-obtain"),
    path("auth/token/refresh/", RefreshView.as_view(), name="token-refresh"),
    path("auth/switch-organization/", SwitchOrganizationView.as_view(), name="switch-organization"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
]
