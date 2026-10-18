from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from apps.people.models import Employee

MISSING_EMAIL = "missing_email"
INVALID_EMAIL = "invalid_email"
DUPLICATE_EMAIL = "duplicate_email"


def employee_face_issues(employee: Employee, duplicate_ids: set) -> list[str]:
    issues: list[str] = []
    if not employee.email:
        issues.append(MISSING_EMAIL)
        return issues
    try:
        validate_email(employee.email)
    except ValidationError:
        issues.append(INVALID_EMAIL)
    if employee.id in duplicate_ids:
        issues.append(DUPLICATE_EMAIL)
    return issues


def duplicate_email_ids(employees: list[Employee]) -> set:
    grouped: dict[str, list] = {}
    for employee in employees:
        if employee.email:
            grouped.setdefault(employee.email.lower(), []).append(employee.id)
    duplicated = set()
    for ids in grouped.values():
        if len(ids) > 1:
            duplicated.update(ids)
    return duplicated


def face_readiness(employees: list[Employee]) -> list[dict]:
    duplicated = duplicate_email_ids(employees)
    report = []
    for employee in employees:
        issues = employee_face_issues(employee, duplicated)
        if not issues:
            continue
        report.append(
            {
                "id": employee.id,
                "document_id": employee.document_id,
                "first_name": employee.first_name,
                "last_name": employee.last_name,
                "email": employee.email,
                "issues": issues,
            }
        )
    return report


def enrollment_blockers(employee: Employee) -> list[str]:
    peers = list(
        Employee.all_objects.filter(organization_id=employee.organization_id).only(
            "id", "email", "document_id", "first_name", "last_name"
        )
    )
    duplicated = duplicate_email_ids(peers)
    return employee_face_issues(employee, duplicated)
