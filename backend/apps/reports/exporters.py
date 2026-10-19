"""Escritura de archivos de asistencia. El trabajo corre en Celery, no en la petición."""

import csv
import json
from pathlib import Path

from apps.reports.engine import summarize

PDF_DETAIL_LIMIT = 1500

COLUMNS = [
    ("work_date", "Fecha"),
    ("document_id", "Documento"),
    ("employee_name", "Empleado"),
    ("department_name", "Departamento"),
    ("site", "Sede"),
    ("status", "Estado"),
    ("expected_start", "Entrada esperada"),
    ("expected_end", "Salida esperada"),
    ("first_in", "Primer ingreso"),
    ("last_out", "Última salida"),
    ("worked_minutes", "Minutos trabajados"),
    ("late_minutes", "Minutos de tardanza"),
    ("early_leave_minutes", "Minutos de salida anticipada"),
    ("orphan_in", "Marca huérfana"),
]


def record_from_row(row) -> dict:
    return {
        "work_date": row.work_date.isoformat(),
        "document_id": row.employee.document_id,
        "employee_name": f"{row.employee.first_name} {row.employee.last_name}",
        "department_name": row.department.name if row.department_id else "",
        "site": row.site,
        "status": row.status,
        "expected_start": _clock(row.expected_start),
        "expected_end": _clock(row.expected_end),
        "first_in": row.first_in.isoformat().replace("+00:00", "Z") if row.first_in else "",
        "last_out": row.last_out.isoformat().replace("+00:00", "Z") if row.last_out else "",
        "worked_minutes": row.worked_minutes,
        "late_minutes": row.late_minutes,
        "early_leave_minutes": row.early_leave_minutes,
        "orphan_in": row.orphan_in,
    }


def write_csv(path: Path, records) -> int:
    count = 0
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([label for _key, label in COLUMNS])
        for record in records:
            writer.writerow([record.get(key, "") for key, _label in COLUMNS])
            count += 1
    return count


def write_xlsx(path: Path, records) -> int:
    from openpyxl import Workbook

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Asistencia")
    sheet.append([label for _key, label in COLUMNS])
    count = 0
    for record in records:
        sheet.append([record.get(key, "") for key, _label in COLUMNS])
        count += 1
    workbook.save(path)
    return count


def write_json(path: Path, summary: dict, records) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        handle.write('{"summary":')
        json.dump(summary, handle, ensure_ascii=False)
        handle.write(',"results":[')
        first = True
        for record in records:
            if not first:
                handle.write(",")
            json.dump(record, handle, ensure_ascii=False)
            first = False
            count += 1
        handle.write("]}")
    return count


def write_pdf(path: Path, summary: dict, records, total: int) -> int:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    story = [
        Paragraph(
            _pdf(f"Asistencia {summary['date_from']} a {summary['date_to']}"),
            styles["Title"],
        ),
        Spacer(1, 8),
        Paragraph(
            _pdf(
                "Días esperados: {expected_days}. Presentes: {present_days}. "
                "Tardanzas: {late_days}. Salidas anticipadas: {early_leave_days}. "
                "Ausencias: {absent_days}. Huérfanas: {incomplete_days}. "
                "Festivos: {holiday_days}. Minutos trabajados: {worked_minutes}."
            ).format(**summary),
            styles["Normal"],
        ),
        Spacer(1, 8),
    ]
    if total > PDF_DETAIL_LIMIT:
        story.append(
            Paragraph(
                _pdf(
                    f"El detalle muestra {PDF_DETAIL_LIMIT} de {total} filas. "
                    "El archivo completo está en CSV, Excel o JSON."
                ),
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 8))
    header = ["Fecha", "Documento", "Empleado", "Estado", "Min", "Tarde", "Anticipada"]
    data = [header]
    shown = 0
    for record in records:
        if shown >= PDF_DETAIL_LIMIT:
            break
        data.append(
            [
                _pdf(record["work_date"]),
                _pdf(record["document_id"]),
                _pdf(record["employee_name"]),
                _pdf(record["status"]),
                str(record["worked_minutes"]),
                str(record["late_minutes"]),
                str(record["early_leave_minutes"]),
            ]
        )
        shown += 1
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1c2836")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e4ddd0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(table)
    document = SimpleDocTemplate(
        str(path),
        pagesize=landscape(A4),
        leftMargin=24,
        rightMargin=24,
        topMargin=24,
        bottomMargin=24,
        title="Asistencia",
    )
    document.build(story)
    return shown


def build_summary(queryset, date_from, date_to) -> dict:
    summary = summarize(queryset, date_from, date_to)
    summary.pop("by_department", None)
    summary.pop("by_day", None)
    return summary


def _clock(value) -> str:
    if value is None:
        return ""
    return value.strftime("%H:%M")


def _pdf(value) -> str:
    return str(value).encode("latin-1", errors="replace").decode("latin-1")
