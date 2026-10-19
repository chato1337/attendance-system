import csv
import json
from datetime import timedelta

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.access.models import AccessLog, Direction
from apps.people.models import Department
from apps.reports.exporters import write_csv
from apps.reports.models import ExportJob, ExportStatus
from apps.reports.tasks import generate_export, purge_expired_exports
from apps.reports.tests.test_attendance import (
    MONDAY,
    _at,
    _department_schedule,
    _employee,
    _log,
    _shift,
)


@pytest.fixture
def export_media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def test_export_endpoint_does_not_build_the_file(monkeypatch, acme_client, export_media):
    seen = {}

    def fake_delay(job_id):
        seen["job_id"] = job_id

    monkeypatch.setattr("apps.reports.views.generate_export.delay", fake_delay)
    response = acme_client.post(
        "/api/v1/reports/exports/",
        {"format": "csv", "date_from": "2026-03-02", "date_to": "2026-03-02"},
        format="json",
    )
    assert response.status_code == 202
    assert response.data["status"] == ExportStatus.PENDING
    assert response.data["download_url"] is None
    assert seen["job_id"]
    job = ExportJob.all_objects.get(id=seen["job_id"])
    assert not job.file


def test_exports_in_four_formats_and_signed_download(
    acme, acme_node, acme_client, globex_client, export_media
):
    department = Department.all_objects.create(organization=acme, name="Operaciones")
    shift = _shift(acme)
    _department_schedule(acme, department, shift)
    ana = _employee(acme, "X-1", department)
    AccessLog.all_objects.bulk_create(
        [
            _log(acme, acme_node, ana, _at(MONDAY, 8, 0), Direction.IN),
            _log(acme, acme_node, ana, _at(MONDAY, 17, 0), Direction.OUT),
        ]
    )
    created = {}
    for export_format in ("csv", "xlsx", "pdf", "json"):
        response = acme_client.post(
            "/api/v1/reports/exports/",
            {
                "format": export_format,
                "date_from": "2026-03-02",
                "date_to": "2026-03-02",
            },
            format="json",
        )
        assert response.status_code == 202, response.data
        assert response.data["status"] == ExportStatus.READY
        assert response.data["row_count"] == 1
        created[export_format] = response.data

    def body(response):
        return b"".join(response.streaming_content)

    csv_response = APIClient().get(f"/api/v1/{created['csv']['download_url']}")
    assert csv_response.status_code == 200
    rows = list(csv.reader(body(csv_response).decode("utf-8-sig").splitlines()))
    assert rows[0][0] == "Fecha"
    assert rows[1][0] == "2026-03-02"
    assert rows[1][1] == "X-1"
    assert "540" in rows[1]

    xlsx_response = APIClient().get(f"/api/v1/{created['xlsx']['download_url']}")
    assert xlsx_response.status_code == 200
    assert body(xlsx_response)[:2] == b"PK"

    pdf_response = APIClient().get(f"/api/v1/{created['pdf']['download_url']}")
    assert pdf_response.status_code == 200
    assert body(pdf_response).startswith(b"%PDF")

    json_response = APIClient().get(f"/api/v1/{created['json']['download_url']}")
    payload = json.loads(body(json_response))
    assert payload["summary"]["worked_minutes"] == 540
    assert payload["results"][0]["document_id"] == "X-1"

    assert globex_client.get("/api/v1/reports/exports/").data["count"] == 0
    foreign = created["csv"]["id"]
    assert globex_client.get(f"/api/v1/reports/exports/{foreign}/").status_code == 404
    assert APIClient().get(f"/api/v1/reports/exports/{foreign}/download/").status_code == 403

    job = ExportJob.all_objects.get(id=foreign)
    job.expires_at = timezone.now() - timedelta(seconds=5)
    job.save(update_fields=["expires_at"])
    expired = APIClient().get(f"/api/v1/{created['csv']['download_url']}")
    assert expired.status_code == 403


def test_viewer_can_request_an_export(viewer_client, export_media, monkeypatch):
    monkeypatch.setattr("apps.reports.views.generate_export.delay", lambda job_id: None)
    response = viewer_client.post(
        "/api/v1/reports/exports/",
        {"format": "json", "date_from": "2026-03-01", "date_to": "2026-03-02"},
        format="json",
    )
    assert response.status_code == 202


def test_failed_export_is_marked(acme, export_media, monkeypatch):
    job = ExportJob.all_objects.create(
        organization=acme,
        export_format="csv",
        filters={"date_from": "2026-03-02", "date_to": "2026-03-02"},
        expires_at=timezone.now() + timedelta(hours=1),
    )

    def explode(*args, **kwargs):
        raise RuntimeError("disco lleno")

    monkeypatch.setattr("apps.reports.tasks.calculate_attendance", explode)
    assert generate_export(str(job.id)) == ExportStatus.FAILED
    job.refresh_from_db()
    assert job.error == "No se pudo generar el archivo."


def test_expired_exports_are_removed(acme, export_media):
    job = ExportJob.all_objects.create(
        organization=acme,
        export_format="csv",
        filters={},
        expires_at=timezone.now() - timedelta(minutes=1),
    )
    job.file.save("viejo.csv", ContentFile("fecha\n"), save=True)
    assert purge_expired_exports() == 1
    assert not ExportJob.all_objects.filter(id=job.id).exists()


def test_csv_writer_handles_one_hundred_thousand_rows(tmp_path):
    def records():
        for index in range(100_000):
            yield {
                "work_date": "2026-01-05",
                "document_id": str(index),
                "employee_name": "Ana Ruiz",
                "department_name": "Operaciones",
                "site": "Sede",
                "status": "PRESENT",
                "expected_start": "08:00",
                "expected_end": "17:00",
                "first_in": "2026-01-05T13:00:00Z",
                "last_out": "2026-01-05T22:00:00Z",
                "worked_minutes": 540,
                "late_minutes": 0,
                "early_leave_minutes": 0,
                "orphan_in": False,
            }

    path = tmp_path / "asistencia.csv"
    assert write_csv(path, records()) == 100_000
    with path.open(encoding="utf-8-sig") as handle:
        assert sum(1 for _ in handle) == 100_001
