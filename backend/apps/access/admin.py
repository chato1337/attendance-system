from django.contrib import admin

from apps.access.models import (
    AccessLog,
    AccessNode,
    Door,
    Reader,
    ReaderProfile,
    Zone,
)
from apps.common.admin import UnscopedAdmin


@admin.register(Zone)
class ZoneAdmin(UnscopedAdmin):
    list_display = ("name", "organization", "is_active", "version")
    list_filter = ("organization", "is_active")
    search_fields = ("name",)


@admin.register(ReaderProfile)
class ReaderProfileAdmin(UnscopedAdmin):
    list_display = ("name", "credential_type", "organization", "is_active", "version")
    list_filter = ("organization", "credential_type", "is_active")
    search_fields = ("name",)


@admin.register(AccessNode)
class AccessNodeAdmin(UnscopedAdmin):
    list_display = ("name", "site", "organization", "is_online", "is_active")
    list_filter = ("organization", "is_online", "is_active")
    search_fields = ("name", "site")
    readonly_fields = ("api_key_hash", "last_heartbeat_at", "last_sync_at")


@admin.register(Door)
class DoorAdmin(UnscopedAdmin):
    list_display = ("name", "node", "direction", "apb_mode", "organization", "is_active")
    list_filter = ("organization", "direction", "apb_mode", "face_enabled", "is_active")
    search_fields = ("name", "relay_device_id")


@admin.register(Reader)
class ReaderAdmin(UnscopedAdmin):
    list_display = ("name", "reader_device_id", "door", "organization", "is_active")
    list_filter = ("organization", "is_active")
    search_fields = ("name", "reader_device_id")


@admin.register(AccessLog)
class AccessLogAdmin(UnscopedAdmin):
    list_display = ("timestamp", "status", "direction", "employee", "node", "organization")
    list_filter = ("organization", "status", "direction", "method", "source")
    search_fields = ("employee__document_id", "employee__last_name", "denial_reason")
    readonly_fields = [field.name for field in AccessLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
