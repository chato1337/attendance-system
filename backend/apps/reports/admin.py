from django.contrib import admin

from apps.common.admin import UnscopedAdmin
from apps.reports.models import DailyAttendance, ExportJob, Holiday, Schedule, Shift


@admin.register(Shift)
class ShiftAdmin(UnscopedAdmin):
    list_display = ("name", "organization", "start_time", "end_time", "is_active")
    list_filter = ("organization", "is_active")
    search_fields = ("name",)


@admin.register(Schedule)
class ScheduleAdmin(UnscopedAdmin):
    list_display = ("shift", "employee", "department", "organization", "is_active")
    list_filter = ("organization", "is_active")


@admin.register(Holiday)
class HolidayAdmin(UnscopedAdmin):
    list_display = ("date", "name", "organization")
    list_filter = ("organization",)
    search_fields = ("name",)


@admin.register(DailyAttendance)
class DailyAttendanceAdmin(UnscopedAdmin):
    list_display = ("work_date", "employee", "status", "site", "worked_minutes", "organization")
    list_filter = ("organization", "status", "work_date")


@admin.register(ExportJob)
class ExportJobAdmin(UnscopedAdmin):
    list_display = ("created_at", "export_format", "status", "row_count", "organization")
    list_filter = ("organization", "status", "export_format")
