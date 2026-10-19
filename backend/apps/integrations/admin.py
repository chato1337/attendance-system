from django.contrib import admin

from apps.common.admin import UnscopedAdmin
from apps.integrations.models import (
    FaceAuthIntegration,
    FaceAuthPendingDeletion,
    PendingFaceIdentity,
)


@admin.register(FaceAuthIntegration)
class FaceAuthIntegrationAdmin(UnscopedAdmin):
    list_display = ("organization", "app_id", "enabled", "allow_panel_login")
    list_filter = ("enabled", "allow_panel_login", "allow_kiosk_self_enrollment")
    search_fields = ("organization__name", "app_id")
    exclude = ("api_key",)


@admin.register(PendingFaceIdentity)
class PendingFaceIdentityAdmin(UnscopedAdmin):
    list_display = ("email", "faceauth_user_id", "organization", "created_at")
    list_filter = ("organization",)
    search_fields = ("email",)


@admin.register(FaceAuthPendingDeletion)
class FaceAuthPendingDeletionAdmin(UnscopedAdmin):
    list_display = ("faceauth_user_id", "reason", "organization", "created_at", "processed_at")
    list_filter = ("organization", "reason")
