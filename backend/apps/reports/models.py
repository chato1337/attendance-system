import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import Activatable
from apps.tenants.models import TenantModel


class Shift(TenantModel, Activatable):
    """Jornada esperada dentro del mismo día civil. No cruza la medianoche."""

    name = models.CharField(max_length=120)
    start_time = models.TimeField()
    end_time = models.TimeField()
    late_tolerance_minutes = models.PositiveIntegerField(default=10)
    early_leave_tolerance_minutes = models.PositiveIntegerField(default=10)

    class Meta:
        verbose_name = "turno"
        verbose_name_plural = "turnos"
        ordering = ["name"]
        base_manager_name = "all_objects"
        default_manager_name = "objects"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="uniq_shift_name_per_org",
            ),
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="shift_same_day",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError("El turno termina el mismo día, después de la hora de entrada.")
        if self.late_tolerance_minutes > 240 or self.early_leave_tolerance_minutes > 240:
            raise ValidationError("La tolerancia no puede superar 240 minutos.")


class Schedule(TenantModel, Activatable):
    """Asigna un turno a un empleado o a un departamento en ciertos días de la semana."""

    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name="schedules")
    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="schedules",
    )
    department = models.ForeignKey(
        "people.Department",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="schedules",
    )
    weekdays = models.JSONField(
        default=list,
        help_text="Días ISO en los que aplica: 1 lunes … 7 domingo.",
    )

    class Meta:
        verbose_name = "horario"
        verbose_name_plural = "horarios"
        ordering = ["shift__name"]
        base_manager_name = "all_objects"
        default_manager_name = "objects"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(employee__isnull=False, department__isnull=True)
                    | models.Q(employee__isnull=True, department__isnull=False)
                ),
                name="schedule_one_target",
            )
        ]

    def __str__(self) -> str:
        target = self.employee or self.department or "sin destino"
        return f"{self.shift} → {target}"

    def clean(self):
        if bool(self.employee_id) == bool(self.department_id):
            raise ValidationError("El horario pertenece a un empleado o a un departamento.")
        days = normalize_weekdays(self.weekdays)
        if not days:
            raise ValidationError("Indique al menos un día de la semana.")
        self.weekdays = days
        if self.shift_id and self.shift.organization_id != self.organization_id:
            raise ValidationError("El turno pertenece a otra organización.")
        if self.employee_id and self.employee.organization_id != self.organization_id:
            raise ValidationError("El empleado pertenece a otra organización.")
        if self.department_id and self.department.organization_id != self.organization_id:
            raise ValidationError("El departamento pertenece a otra organización.")


class Holiday(TenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    date = models.DateField()
    name = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "festivo"
        verbose_name_plural = "festivos"
        ordering = ["-date"]
        base_manager_name = "all_objects"
        default_manager_name = "objects"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "date"],
                name="uniq_holiday_date_per_org",
            )
        ]

    def __str__(self) -> str:
        return f"{self.date:%Y-%m-%d} {self.name}"


class AttendanceStatus(models.TextChoices):
    PRESENT = "PRESENT", "Presente"
    LATE = "LATE", "Tarde"
    EARLY_LEAVE = "EARLY_LEAVE", "Salida anticipada"
    INCOMPLETE = "INCOMPLETE", "Marca huérfana"
    ABSENT = "ABSENT", "Ausente"
    HOLIDAY = "HOLIDAY", "Festivo"


class DailyAttendance(TenantModel):
    """Día de asistencia ya calculado. Se reescribe al recalcular el rango."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.PROTECT,
        related_name="daily_attendance",
    )
    department = models.ForeignKey(
        "people.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_attendance",
    )
    node = models.ForeignKey(
        "access.AccessNode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_attendance",
    )
    site = models.CharField(max_length=150, blank=True)
    work_date = models.DateField()
    status = models.CharField(max_length=20, choices=AttendanceStatus.choices)
    is_holiday = models.BooleanField(default=False)
    scheduled = models.BooleanField(default=False)
    shift = models.ForeignKey(
        Shift,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_attendance",
    )
    expected_start = models.TimeField(null=True, blank=True)
    expected_end = models.TimeField(null=True, blank=True)
    first_in = models.DateTimeField(null=True, blank=True)
    last_out = models.DateTimeField(null=True, blank=True)
    worked_minutes = models.PositiveIntegerField(default=0)
    late_minutes = models.PositiveIntegerField(default=0)
    early_leave_minutes = models.PositiveIntegerField(default=0)
    orphan_in = models.BooleanField(default=False)
    granted_count = models.PositiveIntegerField(default=0)
    calculated_at = models.DateTimeField()

    class Meta:
        verbose_name = "asistencia diaria"
        verbose_name_plural = "asistencias diarias"
        ordering = ["-work_date", "employee__last_name"]
        base_manager_name = "all_objects"
        default_manager_name = "objects"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "employee", "work_date"],
                name="uniq_daily_attendance",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "work_date"], name="attendance_org_date_idx"),
            models.Index(
                fields=["organization", "department", "work_date"],
                name="attendance_dept_date_idx",
            ),
            models.Index(
                fields=["organization", "site", "work_date"],
                name="attendance_site_date_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.work_date} {self.employee} {self.status}"


class ExportFormat(models.TextChoices):
    CSV = "csv", "CSV"
    XLSX = "xlsx", "Excel"
    PDF = "pdf", "PDF"
    JSON = "json", "JSON"


class ExportStatus(models.TextChoices):
    PENDING = "PENDING", "Pendiente"
    RUNNING = "RUNNING", "En curso"
    READY = "READY", "Listo"
    FAILED = "FAILED", "Fallido"


class ExportJob(TenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="export_jobs",
    )
    export_format = models.CharField(max_length=8, choices=ExportFormat.choices)
    status = models.CharField(
        max_length=12,
        choices=ExportStatus.choices,
        default=ExportStatus.PENDING,
    )
    filters = models.JSONField(default=dict, blank=True)
    file = models.FileField(upload_to="exports/%Y/%m/", blank=True)
    error = models.TextField(blank=True)
    row_count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "exportación"
        verbose_name_plural = "exportaciones"
        ordering = ["-created_at"]
        base_manager_name = "all_objects"
        default_manager_name = "objects"

    def __str__(self) -> str:
        return f"{self.export_format} {self.status}"


def normalize_weekdays(value) -> list[int]:
    if not isinstance(value, list):
        return []
    days: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item not in range(1, 8):
            return []
        if item not in days:
            days.append(item)
    return days
