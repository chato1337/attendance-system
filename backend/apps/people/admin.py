from django.contrib import admin

from apps.common.admin import UnscopedAdmin
from apps.people.models import Credential, Department, Employee


@admin.register(Department)
class DepartmentAdmin(UnscopedAdmin):
    list_display = ("name", "organization", "is_active", "version")
    list_filter = ("organization", "is_active")
    search_fields = ("name",)


@admin.register(Employee)
class EmployeeAdmin(UnscopedAdmin):
    list_display = (
        "document_id",
        "first_name",
        "last_name",
        "organization",
        "is_active",
        "version",
    )
    list_filter = ("organization", "is_active", "is_inside", "department")
    search_fields = ("document_id", "first_name", "last_name", "email")


@admin.register(Credential)
class CredentialAdmin(UnscopedAdmin):
    list_display = ("type", "payload", "employee", "organization", "is_active", "version")
    list_filter = ("organization", "type", "is_active", "source")
    search_fields = ("payload", "employee__document_id", "employee__last_name")
