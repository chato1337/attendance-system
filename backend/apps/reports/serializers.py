from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from apps.common.mixins import ReactivationMixin
from apps.people.models import Department, Employee
from apps.reports.models import (
    AttendanceStatus,
    DailyAttendance,
    ExportFormat,
    ExportJob,
    ExportStatus,
    Holiday,
    Schedule,
    Shift,
    normalize_weekdays,
)
from apps.reports.signing import sign_export
from apps.tenants.context import get_current_organization


def validate_report_range(attrs):
    start = attrs["date_from"]
    end = attrs["date_to"]
    if end < start:
        raise serializers.ValidationError("La fecha final es anterior a la inicial.")
    days = (end - start).days + 1
    if days > settings.REPORT_RANGE_MAX_DAYS:
        raise serializers.ValidationError(
            f"El rango máximo es de {settings.REPORT_RANGE_MAX_DAYS} días."
        )
    return attrs


class ShiftSerializer(ReactivationMixin, serializers.ModelSerializer):
    class Meta:
        model = Shift
        fields = [
            "id",
            "organization",
            "name",
            "start_time",
            "end_time",
            "late_tolerance_minutes",
            "early_leave_tolerance_minutes",
            "is_active",
            "deleted_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "organization", "deleted_at", "created_at", "updated_at"]
        extra_kwargs = {
            "late_tolerance_minutes": {"min_value": 0, "max_value": 240},
            "early_leave_tolerance_minutes": {"min_value": 0, "max_value": 240},
        }

    def validate_name(self, value):
        organization = get_current_organization()
        queryset = Shift.all_objects.filter(organization=organization, name=value)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("Ya existe un turno con ese nombre.")
        return value

    def validate(self, attrs):
        start = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if start and end and end <= start:
            raise serializers.ValidationError(
                "El turno termina el mismo día, después de la hora de entrada."
            )
        return attrs


class ScheduleSerializer(ReactivationMixin, serializers.ModelSerializer):
    shift_name = serializers.CharField(source="shift.name", read_only=True)
    employee_name = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()

    class Meta:
        model = Schedule
        fields = [
            "id",
            "organization",
            "shift",
            "shift_name",
            "employee",
            "employee_name",
            "department",
            "department_name",
            "weekdays",
            "is_active",
            "deleted_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "shift_name",
            "employee_name",
            "department_name",
            "deleted_at",
            "created_at",
            "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organization = get_current_organization()
        if organization is None:
            return
        self.fields["shift"].queryset = Shift.all_objects.filter(organization=organization)
        self.fields["employee"].queryset = Employee.all_objects.filter(organization=organization)
        self.fields["department"].queryset = Department.all_objects.filter(
            organization=organization
        )

    def get_employee_name(self, obj) -> str:
        if obj.employee_id is None:
            return ""
        return f"{obj.employee.first_name} {obj.employee.last_name}"

    def get_department_name(self, obj) -> str:
        if obj.department_id is None:
            return ""
        return obj.department.name

    def validate(self, attrs):
        if self.instance is None:
            employee = attrs.get("employee")
            department = attrs.get("department")
            weekdays = attrs.get("weekdays")
        else:
            employee = attrs["employee"] if "employee" in attrs else self.instance.employee
            department = attrs["department"] if "department" in attrs else self.instance.department
            weekdays = attrs.get("weekdays", self.instance.weekdays)
        if bool(employee) == bool(department):
            raise serializers.ValidationError(
                "El horario pertenece a un empleado o a un departamento, no a ambos."
            )
        days = normalize_weekdays(weekdays)
        if not days:
            raise serializers.ValidationError(
                {"weekdays": "Indique días del 1 (lunes) al 7 (domingo)."}
            )
        attrs["weekdays"] = days
        return attrs


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = ["id", "organization", "date", "name", "created_at"]
        read_only_fields = ["id", "organization", "created_at"]

    def validate_date(self, value):
        organization = get_current_organization()
        queryset = Holiday.all_objects.filter(organization=organization, date=value)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("Esa fecha ya es festivo.")
        return value


class DailyAttendanceSerializer(serializers.ModelSerializer):
    document_id = serializers.CharField(source="employee.document_id", read_only=True)
    employee_name = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()

    class Meta:
        model = DailyAttendance
        fields = [
            "id",
            "employee",
            "document_id",
            "employee_name",
            "department",
            "department_name",
            "site",
            "work_date",
            "status",
            "is_holiday",
            "scheduled",
            "expected_start",
            "expected_end",
            "first_in",
            "last_out",
            "worked_minutes",
            "late_minutes",
            "early_leave_minutes",
            "orphan_in",
            "granted_count",
        ]

    def get_employee_name(self, obj) -> str:
        return f"{obj.employee.first_name} {obj.employee.last_name}"

    def get_department_name(self, obj) -> str:
        if obj.department_id is None:
            return "Sin departamento"
        return obj.department.name


class ReportFilterSerializer(serializers.Serializer):
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    department = serializers.UUIDField(required=False, allow_null=True)
    employee = serializers.UUIDField(required=False, allow_null=True)
    site = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        validate_report_range(attrs)
        status = attrs.get("status") or ""
        if status and status not in AttendanceStatus.values:
            raise serializers.ValidationError({"status": "Estado desconocido."})
        attrs["status"] = status
        attrs["site"] = attrs.get("site") or ""
        attrs["department"] = attrs.get("department")
        attrs["employee"] = attrs.get("employee")
        return attrs


class RecalculateSerializer(serializers.Serializer):
    date_from = serializers.DateField()
    date_to = serializers.DateField()

    def validate(self, attrs):
        return validate_report_range(attrs)


class ExportCreateSerializer(ReportFilterSerializer):
    format = serializers.ChoiceField(choices=ExportFormat.choices)


class ExportJobSerializer(serializers.ModelSerializer):
    format = serializers.CharField(source="export_format", read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = ExportJob
        fields = [
            "id",
            "format",
            "status",
            "filters",
            "row_count",
            "error",
            "download_url",
            "expires_at",
            "created_at",
        ]

    def get_download_url(self, obj) -> str | None:
        if obj.status != ExportStatus.READY or not obj.file:
            return None
        if obj.expires_at < timezone.now():
            return None
        token = sign_export(obj.id)
        return f"reports/exports/{obj.id}/download/?token={token}"


def filters_payload(data) -> dict:
    return {
        "date_from": data["date_from"].isoformat(),
        "date_to": data["date_to"].isoformat(),
        "department": str(data["department"]) if data.get("department") else None,
        "employee": str(data["employee"]) if data.get("employee") else None,
        "site": data.get("site") or "",
        "status": data.get("status") or "",
    }
