"""Importación masiva de empleados (JSON o filas CSV ya parseadas)."""

from __future__ import annotations

from django.db import transaction

from apps.people.models import Department, Employee
from apps.tenants.context import get_current_organization


def upsert_employees(rows: list[dict]) -> dict:
    organization = get_current_organization()
    created = 0
    updated = 0
    errors: list[dict] = []
    departments = {
        item.name.lower(): item
        for item in Department.all_objects.filter(organization=organization, is_active=True)
    }

    with transaction.atomic():
        for index, raw in enumerate(rows):
            try:
                document_id = str(raw.get("document_id") or "").strip()
                first_name = str(raw.get("first_name") or "").strip()
                last_name = str(raw.get("last_name") or "").strip()
                if not document_id or not first_name or not last_name:
                    raise ValueError("document_id, first_name y last_name son obligatorios.")
                email = str(raw.get("email") or "").strip().lower() or None
                department_name = str(raw.get("department") or "").strip()
                department = None
                if department_name:
                    key = department_name.lower()
                    department = departments.get(key)
                    if department is None:
                        department = Department.all_objects.create(
                            organization=organization,
                            name=department_name,
                        )
                        departments[key] = department
                is_active = _bool(raw.get("is_active"), default=True)
                employee = Employee.all_objects.filter(
                    organization=organization,
                    document_id=document_id,
                ).first()
                if employee is None:
                    Employee.all_objects.create(
                        organization=organization,
                        department=department,
                        document_id=document_id,
                        first_name=first_name,
                        last_name=last_name,
                        email=email,
                        is_active=is_active,
                    )
                    created += 1
                else:
                    employee.department = department
                    employee.first_name = first_name
                    employee.last_name = last_name
                    employee.email = email
                    employee.is_active = is_active
                    if is_active:
                        employee.deleted_at = None
                    employee.save()
                    updated += 1
            except Exception as exc:
                errors.append(
                    {
                        "index": index,
                        "document_id": raw.get("document_id"),
                        "error": str(exc),
                    }
                )

    return {
        "created": created,
        "updated": updated,
        "errors": errors,
        "count": created + updated,
    }


def _bool(value, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "si", "sí", "activo"}:
        return True
    if text in {"0", "false", "no", "inactivo"}:
        return False
    raise ValueError(f"Valor booleano inválido: {value}")
