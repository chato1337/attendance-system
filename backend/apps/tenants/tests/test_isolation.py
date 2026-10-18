from django.utils import timezone

from apps.access.models import (
    AccessLog,
    AccessMethod,
    AccessNode,
    AccessSource,
    AccessStatus,
    Direction,
    Door,
    Reader,
    ReaderProfile,
)
from apps.common.secrets import generate_secret
from apps.kiosk.models import FaceEnrollmentSession, Kiosk
from apps.people.models import Credential, Department, Employee
from apps.tenants.context import get_current_organization, set_current_organization
from apps.tenants.models import Membership


def _build(org, document_id, device_id):
    department = Department.all_objects.create(organization=org, name=f"Depto {document_id}")
    employee = Employee.all_objects.create(
        organization=org,
        department=department,
        document_id=document_id,
        first_name="Ana",
        last_name=org.slug,
        email=f"{document_id}@{org.slug}.test",
    )
    profile = ReaderProfile.all_objects.filter(organization=org, credential_type="RFID").first()
    credential = Credential.all_objects.create(
        organization=org,
        employee=employee,
        type=Credential.CredentialType.RFID,
        payload=f"CARD{document_id}",
        reader_profile=profile,
    )
    node_key, node_hash = generate_secret()
    node = AccessNode.all_objects.create(
        organization=org,
        name=f"Nodo {document_id}",
        site="Sede",
        timezone="America/Bogota",
        api_key_hash=node_hash,
    )
    door = Door.all_objects.create(
        organization=org,
        node=node,
        name=f"Puerta {document_id}",
        relay_device_id=f"REL{document_id}",
        direction=Direction.IN,
    )
    reader = Reader.all_objects.create(
        organization=org,
        door=door,
        reader_profile=profile,
        name=f"Lector {document_id}",
        reader_device_id=device_id,
    )
    _token, token_hash = generate_secret()
    kiosk = Kiosk.all_objects.create(
        organization=org,
        door=door,
        name=f"Kiosco {document_id}",
        kiosk_token_hash=token_hash,
    )
    log = AccessLog.all_objects.create(
        organization=org,
        node=node,
        door=door,
        employee=employee,
        credential=credential,
        timestamp=timezone.now(),
        direction=Direction.IN,
        status=AccessStatus.GRANTED,
        method=AccessMethod.RFID,
        source=AccessSource.GATEWAY,
    )
    session = FaceEnrollmentSession.all_objects.create(
        organization=org,
        employee=employee,
        started_by=FaceEnrollmentSession.StartedBy.USER,
    )
    membership = Membership.objects.get(user__username="globex.admin", organization=org)
    return {
        f"/api/v1/departments/{department.id}/": department,
        f"/api/v1/employees/{employee.id}/": employee,
        f"/api/v1/credentials/{credential.id}/": credential,
        f"/api/v1/reader-profiles/{profile.id}/": profile,
        f"/api/v1/nodes/{node.id}/": node,
        f"/api/v1/doors/{door.id}/": door,
        f"/api/v1/readers/{reader.id}/": reader,
        f"/api/v1/kiosks/{kiosk.id}/": kiosk,
        f"/api/v1/access-logs/{log.id}/": log,
        f"/api/v1/face-enrollment-sessions/{session.id}/": session,
        f"/api/v1/memberships/{membership.id}/": membership,
        "node_key": node_key,
    }


def test_manager_returns_nothing_without_tenant_context(acme):
    Employee.all_objects.create(
        organization=acme,
        document_id="1",
        first_name="Ana",
        last_name="Ruiz",
    )
    assert Employee.objects.count() == 0
    set_current_organization(acme)
    try:
        assert Employee.objects.count() == 1
    finally:
        set_current_organization(None)
        assert get_current_organization() is None


def test_other_organization_is_not_readable_by_id(acme_client, globex, globex_admin):
    assert globex_admin.memberships.filter(organization=globex).exists()
    resources = _build(globex, "900", "COM9")
    for url in resources:
        if not url.startswith("/"):
            continue
        response = acme_client.get(url)
        assert response.status_code == 404, url
        assert response.data["detail"] == "No encontrado."


def test_list_does_not_leak_other_organization(acme_client, acme, globex):
    Employee.all_objects.create(
        organization=acme,
        document_id="1",
        first_name="Ana",
        last_name="Acme",
    )
    hidden = Employee.all_objects.create(
        organization=globex,
        document_id="1",
        first_name="Bruno",
        last_name="Globex",
    )
    response = acme_client.get("/api/v1/employees/")
    assert response.status_code == 200
    ids = {item["id"] for item in response.data["results"]}
    assert str(hidden.id) not in ids
    assert len(ids) == 1


def test_client_cannot_assign_another_organization(acme_client, acme, globex):
    response = acme_client.post(
        "/api/v1/employees/",
        {
            "document_id": "77",
            "first_name": "Nueva",
            "last_name": "Persona",
            "organization": str(globex.id),
        },
        format="json",
    )
    assert response.status_code == 201
    created = Employee.all_objects.get(document_id="77")
    assert created.organization_id == acme.id


def test_tenant_context_is_cleared_after_the_request(acme_client, acme):
    Employee.all_objects.create(
        organization=acme,
        document_id="1",
        first_name="Ana",
        last_name="Ruiz",
    )
    assert acme_client.get("/api/v1/employees/").status_code == 200
    assert get_current_organization() is None
