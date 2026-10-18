from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.accounts.models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "is_superadmin", "is_staff", "is_active")
    list_filter = ("is_superadmin", "is_staff", "is_active")
    search_fields = ("username", "email", "first_name", "last_name")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Plataforma", {"fields": ("is_superadmin", "faceauth_user_id")}),
    )
