import logging
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.people.models import Employee
from apps.reports.engine import attendance_queryset, calculate_attendance
from apps.reports.exporters import (
    build_summary,
    record_from_row,
    write_csv,
    write_json,
    write_pdf,
    write_xlsx,
)
from apps.reports.models import ExportFormat, ExportJob, ExportStatus
from apps.tenants.models import Organization

logger = logging.getLogger(__name__)

WRITERS = {
    ExportFormat.CSV: write_csv,
    ExportFormat.XLSX: write_xlsx,
    ExportFormat.JSON: write_json,
    ExportFormat.PDF: write_pdf,
}


@shared_task(name="apps.reports.tasks.rebuild_daily_attendance")
def rebuild_daily_attendance() -> int:
    now = timezone.now()
    processed = 0
    for organization in Organization.objects.filter(is_active=True):
        local_today = now.astimezone(ZoneInfo(organization.timezone)).date()
        calculate_attendance(organization, local_today - timedelta(days=1), local_today)
        processed += 1
    purge_expired_exports()
    return processed


@shared_task(name="apps.reports.tasks.generate_export")
def generate_export(job_id: str) -> str:
    job = ExportJob.all_objects.select_related("organization").get(id=job_id)
    job.status = ExportStatus.RUNNING
    job.error = ""
    job.save(update_fields=["status", "error"])
    try:
        filters = parse_filters(job.filters)
        employee_ids = _employee_ids(job.organization, filters)
        calculate_attendance(
            job.organization,
            filters["date_from"],
            filters["date_to"],
            employee_ids=employee_ids,
        )
        queryset = attendance_queryset(job.organization, filters).select_related(
            "employee", "department"
        )
        summary = build_summary(queryset, filters["date_from"], filters["date_to"])
        relative = _relative_path(job)
        absolute = Path(settings.MEDIA_ROOT) / relative
        absolute.parent.mkdir(parents=True, exist_ok=True)
        ordered = queryset.order_by("work_date", "employee__last_name", "employee__first_name")
        records = (record_from_row(row) for row in ordered.iterator(chunk_size=1000))
        if job.export_format == ExportFormat.PDF:
            job.row_count = queryset.count()
            write_pdf(absolute, summary, records, job.row_count)
        elif job.export_format == ExportFormat.JSON:
            job.row_count = write_json(absolute, summary, records)
        else:
            job.row_count = WRITERS[job.export_format](absolute, records)
        job.file.name = relative.as_posix()
        job.status = ExportStatus.READY
        job.save(update_fields=["file", "status", "row_count", "error"])
    except Exception:
        logger.exception("No se pudo generar la exportación %s", job_id)
        job.status = ExportStatus.FAILED
        job.error = "No se pudo generar el archivo."
        job.save(update_fields=["status", "error"])
    return job.status


def parse_filters(raw: dict) -> dict:
    return {
        "date_from": date.fromisoformat(raw["date_from"]),
        "date_to": date.fromisoformat(raw["date_to"]),
        "department": raw.get("department") or None,
        "employee": raw.get("employee") or None,
        "site": raw.get("site") or "",
        "status": raw.get("status") or "",
    }


def purge_expired_exports() -> int:
    expired = ExportJob.all_objects.filter(expires_at__lt=timezone.now())
    removed = 0
    for job in expired.iterator():
        if job.file:
            job.file.delete(save=False)
        job.delete()
        removed += 1
    return removed


def _employee_ids(organization, filters):
    if filters.get("employee"):
        return [filters["employee"]]
    if filters.get("department"):
        return list(
            Employee.all_objects.filter(
                organization=organization,
                is_active=True,
                department_id=filters["department"],
            ).values_list("id", flat=True)
        )
    return None


def _relative_path(job: ExportJob):
    return Path("exports") / f"{job.id}.{job.export_format}"
