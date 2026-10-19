from django.contrib import admin

from apps.common.admin import UnscopedAdmin
from apps.integrations.models import (
    APIToken,
    FaceAuthIntegration,
    FaceAuthPendingDeletion,
    PendingFaceIdentity,
    WebhookDelivery,
    WebhookSubscription,
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


@admin.register(WebhookSubscription)
class WebhookSubscriptionAdmin(UnscopedAdmin):
    list_display = ("name", "organization", "url", "is_active", "updated_at")
    list_filter = ("is_active", "organization")
    search_fields = ("name", "url")
    exclude = ("secret",)


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(UnscopedAdmin):
    list_display = ("event", "status", "attempt", "subscription", "organization", "created_at")
    list_filter = ("status", "event", "organization")
    search_fields = ("id",)


@admin.register(APIToken)
class APITokenAdmin(UnscopedAdmin):
    list_display = ("name", "token_prefix", "organization", "is_active", "last_used_at")
    list_filter = ("is_active", "organization")
    search_fields = ("name", "token_prefix")
    exclude = ("token_hash",)
