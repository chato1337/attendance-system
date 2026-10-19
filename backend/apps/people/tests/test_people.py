import uuid

import pytest
from django.db import IntegrityError, transaction

from apps.people.models import Credential, Employee


def test_credentials_can_be_listed_by_employee(acme_client, acme, globex):
    owner = Employee.all_objects.create(
        organization=acme, document_id="F4", first_name="Panel", last_name="Prueba"
    )
    other = Employee.all_objects.create(
        organization=acme, document_id="F5", first_name="Otra", last_name="Persona"
    )
    foreign = Employee.all_objects.create(
        organization=globex, document_id="F4", first_name="Bruno", last_name="Díaz"
    )
    Credential.all_objects.create(
        organization=acme,
        employee=owner,
        type=Credential.CredentialType.RFID,
        payload="00AB12",
    )
    Credential.all_objects.create(
        organization=acme,
        employee=other,
        type=Credential.CredentialType.RFID,
        payload="00CD34",
    )
    listed = acme_client.get(f"/api/v1/credentials/?employee={owner.id}")
    assert listed.status_code == 200
    assert [row["payload"] for row in listed.data["results"]] == ["00AB12"]
    unknown = acme_client.get(f"/api/v1/credentials/?employee={uuid.uuid4()}")
    assert unknown.status_code == 200
    assert unknown.data["results"] == []
    isolated = acme_client.get(f"/api/v1/credentials/?employee={foreign.id}")
    assert isolated.status_code == 200
    assert isolated.data["results"] == []
    invalid = acme_client.get("/api/v1/credentials/?employee=no-es-uuid")
    assert invalid.status_code == 400


def test_viewer_cannot_mutate_employees(viewer_client):
    payload = {"document_id": "10", "first_name": "Vio", "last_name": "Leta"}
    assert viewer_client.post("/api/v1/employees/", payload, format="json").status_code == 403
    assert viewer_client.patch("/api/v1/employees/", {}, format="json").status_code == 403


def test_operator_can_create_and_search_employees(operator_client):
    created = operator_client.post(
        "/api/v1/employees/",
        {
            "document_id": "ZZ-9",
            "first_name": "Olivia",
            "last_name": "Paz",
            "email": "Olivia@Acme.test",
        },
        format="json",
    )
    assert created.status_code == 201
    assert created.data["email"] == "olivia@acme.test"
    assert created.data["version"] > 0
    listed = operator_client.get("/api/v1/employees/?search=ZZ-9&page_size=1")
    assert listed.status_code == 200
    assert listed.data["results"][0]["document_id"] == "ZZ-9"


def test_soft_delete_keeps_the_row_and_blocks_document_reuse(acme_client, acme):
    created = acme_client.post(
        "/api/v1/employees/",
        {"document_id": "42", "first_name": "Ana", "last_name": "Ruiz"},
        format="json",
    )
    employee_id = created.data["id"]
    version = created.data["version"]
    deleted = acme_client.delete(f"/api/v1/employees/{employee_id}/")
    assert deleted.status_code == 204
    again = acme_client.get(f"/api/v1/employees/{employee_id}/")
    assert again.status_code == 200
    assert again.data["is_active"] is False
    assert again.data["deleted_at"] is not None
    assert again.data["version"] > version
    duplicate = acme_client.post(
        "/api/v1/employees/",
        {"document_id": "42", "first_name": "Otra", "last_name": "Persona"},
        format="json",
    )
    assert duplicate.status_code == 400


def test_same_document_can_exist_in_another_organization(acme, globex):
    Employee.all_objects.create(
        organization=acme, document_id="42", first_name="Ana", last_name="Ruiz"
    )
    Employee.all_objects.create(
        organization=globex, document_id="42", first_name="Bruno", last_name="Díaz"
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Employee.all_objects.create(
            organization=acme, document_id="42", first_name="Otra", last_name="Ana"
        )


def test_reactivation_clears_deleted_at(acme_client):
    created = acme_client.post(
        "/api/v1/departments/",
        {"name": "Operaciones"},
        format="json",
    )
    department_id = created.data["id"]
    assert acme_client.delete(f"/api/v1/departments/{department_id}/").status_code == 204
    restored = acme_client.patch(
        f"/api/v1/departments/{department_id}/",
        {"is_active": True},
        format="json",
    )
    assert restored.status_code == 200
    assert restored.data["is_active"] is True
    assert restored.data["deleted_at"] is None


def test_facial_payload_must_be_uuid_and_inactive_payload_can_be_reused(acme_client, acme):
    employee = Employee.all_objects.create(
        organization=acme,
        document_id="7",
        first_name="Ana",
        last_name="Ruiz",
        email="ana@acme.test",
    )
    rejected = acme_client.post(
        "/api/v1/credentials/",
        {"employee": str(employee.id), "type": "FACIAL", "payload": "no-es-uuid"},
        format="json",
    )
    assert rejected.status_code == 400
    face_id = str(uuid.uuid4())
    created = acme_client.post(
        "/api/v1/credentials/",
        {"employee": str(employee.id), "type": "FACIAL", "payload": face_id, "source": "FACEAUTH"},
        format="json",
    )
    assert created.status_code == 201
    assert acme_client.delete(f"/api/v1/credentials/{created.data['id']}/").status_code == 204
    reused = acme_client.post(
        "/api/v1/credentials/",
        {"employee": str(employee.id), "type": "FACIAL", "payload": face_id},
        format="json",
    )
    assert reused.status_code == 201
    with pytest.raises(IntegrityError), transaction.atomic():
        Credential.all_objects.create(
            organization=acme,
            employee=employee,
            type=Credential.CredentialType.FACIAL,
            payload=face_id,
        )


def test_face_readiness_and_enrollment_validation(acme_client, acme):
    ready = Employee.all_objects.create(
        organization=acme,
        document_id="1",
        first_name="Ana",
        last_name="Ruiz",
        email="ana@acme.test",
    )
    Employee.all_objects.create(
        organization=acme,
        document_id="2",
        first_name="Luis",
        last_name="Peña",
    )
    Employee.all_objects.create(
        organization=acme,
        document_id="3",
        first_name="Marta",
        last_name="Díaz",
        email="duplicado@acme.test",
    )
    Employee.all_objects.create(
        organization=acme,
        document_id="4",
        first_name="Nora",
        last_name="Díaz",
        email="duplicado@acme.test",
    )
    invalid = Employee.all_objects.create(
        organization=acme,
        document_id="5",
        first_name="Ivo",
        last_name="Nulo",
        email="ivo@acme.test",
    )
    Employee.all_objects.filter(pk=invalid.pk).update(email="no-es-email")

    report = acme_client.get("/api/v1/employees/face-readiness/")
    assert report.status_code == 200
    by_document = {row["document_id"]: row["issues"] for row in report.data["results"]}
    assert "1" not in by_document
    assert by_document["2"] == ["missing_email"]
    assert "duplicate_email" in by_document["3"]
    assert "duplicate_email" in by_document["4"]
    assert "invalid_email" in by_document["5"]

    blocked = acme_client.post(f"/api/v1/employees/{invalid.id}/face-enrollment-sessions/")
    assert blocked.status_code == 400
    assert "invalid_email" in blocked.data["issues"]
    started = acme_client.post(f"/api/v1/employees/{ready.id}/face-enrollment-sessions/")
    assert started.status_code == 201
    assert started.data["status"] == "PENDING"
    assert started.data["employee"] == ready.id
    assert (
        acme_client.get(f"/api/v1/face-enrollment-sessions/{started.data['id']}/").status_code
        == 200
    )
