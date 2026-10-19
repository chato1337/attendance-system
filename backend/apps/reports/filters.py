import django_filters

from apps.reports.models import DailyAttendance, Holiday, Schedule, Shift


class ShiftFilter(django_filters.FilterSet):
    class Meta:
        model = Shift
        fields = ["is_active"]


class ScheduleFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter(field_name="employee_id")
    department = django_filters.UUIDFilter(field_name="department_id")
    shift = django_filters.UUIDFilter(field_name="shift_id")

    class Meta:
        model = Schedule
        fields = ["employee", "department", "shift", "is_active"]


class HolidayFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="date", lookup_expr="lte")

    class Meta:
        model = Holiday
        fields = ["date"]


class AttendanceFilter(django_filters.FilterSet):
    department = django_filters.UUIDFilter(field_name="department_id")
    employee = django_filters.UUIDFilter(field_name="employee_id")
    date_from = django_filters.DateFilter(field_name="work_date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="work_date", lookup_expr="lte")

    class Meta:
        model = DailyAttendance
        fields = ["department", "employee", "site", "status", "date_from", "date_to"]
