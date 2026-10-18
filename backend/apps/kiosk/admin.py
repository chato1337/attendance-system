from django.contrib import admin

from apps.common.admin import UnscopedAdmin
from apps.kiosk.models import FaceEnrollmentSession, Kiosk


@admin.register(Kiosk)
class KioskAdmin(UnscopedAdmin):
    list_display = ("name", "door", "organization", "is_active", "last_seen_at")
    list_filter = ("organization", "is_active")
    search_fields = ("name",)
    readonly_fields = ("kiosk_token_hash",)


@admin.register(FaceEnrollmentSession)
class FaceEnrollmentSessionAdmin(UnscopedAdmin):
    list_display = ("employee", "status", "started_by", "organization", "created_at", "expires_at")
    list_filter = ("organization", "status", "started_by")
    search_fields = ("employee__document_id", "employee__last_name")
