import json

from rest_framework.test import APIClient

from apps.access.models import AccessNode, Door, ReaderProfile
from apps.common.secrets import generate_secret
from apps.people.models import Credential, Employee
from apps.tenants.context import set_current_organization


def test_invalid_node_key_is_rejected(acme_node):
    client = APIClient()
    response = client.get("/api/v1/edge/sync/delta/")
    assert response.status_code == 401
    client.credentials(HTTP_AUTHORIZATION="Bearer no-es-una-llave")
    denied = client.get("/api/v1/edge/sync/delta/")
    assert denied.status_code == 401
    acme_node.is_active = False
    acme_node.save(update_fields=["is_active", "updated_at"])
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {acme_node.plaintext_api_key}")
    inactive = client.get("/api/v1/edge/sync/delta/")
    assert inactive.status_code == 401


def test_node_key_does_not_open_the_panel_and_jwt_does_not_open_the_edge(node_client, acme_client):
    assert node_client.get("/api/v1/employees/").status_code == 401
    assert acme_client.get("/api/v1/edge/sync/delta/").status_code == 401


def test_delta_is_scoped_to_the_node_and_includes_inactive_rows(
    node_client, acme, acme_node, acme_employee, acme_door, acme_reader, globex, globex_node
):
    set_current_organization(None)
    foreign = Employee.all_objects.create(
        organization=globex,
        document_id="900",
        first_name="Gloria",
        last_name="Rex",
    )
    credential = Credential.all_objects.create(
        organization=acme,
        employee=acme_employee,
        type=Credential.CredentialType.RFID,
        payload="AABBCCDD",
    )
    Door.all_objects.create(
        organization=globex,
        node=globex_node,
        name="Ajena",
        relay_device_id="RELAY9",
        direction="OUT",
    )
    _plain, digest = generate_secret()
    other_node = AccessNode.all_objects.create(
        organization=acme,
        name="Sede Sur",
        api_key_hash=digest,
    )
    other_door = Door.all_objects.create(
        organization=acme,
        node=other_node,
        name="Otra sede",
        relay_device_id="RELAY2",
        direction="OUT",
    )
    first = node_client.get("/api/v1/edge/sync/delta/?since_version=0&limit=1")
    assert first.status_code == 200
    assert first.data["has_more"] is True
    assert first.data["server_time"].endswith("Z")
    acme_node.refresh_from_db()
    assert acme_node.last_sync_at is not None

    seen = {"employees": [], "credentials": [], "reader_profiles": [], "doors": [], "readers": []}
    cursor = 0
    pages = 0
    while True:
        page = node_client.get(f"/api/v1/edge/sync/delta/?since_version={cursor}&limit=1")
        assert page.status_code == 200
        for key in seen:
            seen[key].extend(page.data[key])
        cursor = page.data["next_since_version"]
        pages += 1
        if not page.data["has_more"]:
            break
        assert pages < 50
    assert page.data["next_since_version"] == page.data["current_version"]

    employee_ids = {row["id"] for row in seen["employees"]}
    door_ids = {row["id"] for row in seen["doors"]}
    globex_profiles = {
        str(item)
        for item in ReaderProfile.all_objects.filter(organization=globex).values_list(
            "id", flat=True
        )
    }
    assert globex_profiles.isdisjoint({row["id"] for row in seen["reader_profiles"]})
    assert str(acme_employee.id) in employee_ids
    assert str(foreign.id) not in employee_ids
    assert str(acme_door.id) in door_ids
    assert str(other_door.id) not in door_ids
    assert {row["id"] for row in seen["readers"]} == {str(acme_reader.id)}
    assert any(row["id"] == str(credential.id) and row["is_active"] for row in seen["credentials"])

    before = credential.version
    credential.is_active = False
    credential.save()
    incremental = node_client.get(f"/api/v1/edge/sync/delta/?since_version={before}")
    matched = [row for row in incremental.data["credentials"] if row["id"] == str(credential.id)]
    assert matched[0]["is_active"] is False
    caught_up = node_client.get(
        f"/api/v1/edge/sync/delta/?since_version={incremental.data['current_version']}"
    )
    assert caught_up.status_code == 200
    assert caught_up.data["has_more"] is False
    assert caught_up.data["employees"] == []


def test_delta_rejects_bad_query_params(node_client):
    assert node_client.get("/api/v1/edge/sync/delta/?since_version=-1").status_code == 400
    assert node_client.get("/api/v1/edge/sync/delta/?limit=abc").status_code == 400


def test_openapi_includes_the_edge_protocol(db):
    client = APIClient()
    response = client.get("/api/schema/", {"format": "json"})
    assert response.status_code == 200
    paths = json.loads(response.content)["paths"]
    for path in (
        "/api/v1/edge/sync/delta/",
        "/api/v1/edge/logs/batch/",
        "/api/v1/edge/heartbeat/",
        "/api/v1/edge/commands/",
    ):
        assert path in paths


def test_inactive_organization_cannot_sync(node_client, acme):
    acme.is_active = False
    acme.save(update_fields=["is_active", "updated_at"])
    assert node_client.get("/api/v1/edge/sync/delta/").status_code == 401
