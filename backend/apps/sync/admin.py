from django.contrib import admin

from apps.common.admin import UnscopedAdmin
from apps.sync.models import EdgeCommand


@admin.register(EdgeCommand)
class EdgeCommandAdmin(UnscopedAdmin):
    list_display = ("created_at", "type", "status", "node", "organization", "expires_at")
    list_filter = ("organization", "type", "status")
    search_fields = ("node__name", "id")
    readonly_fields = [field.name for field in EdgeCommand._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
