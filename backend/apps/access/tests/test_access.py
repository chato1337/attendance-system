from apps.access.models import AccessNode, Door, ReaderProfile
from apps.common.secrets import hash_secret
from apps.people.models import Credential, Employee


def test_versions_are_globally_monotonic(acme, globex):
    first = Employee.all_objects.create(
        organization=acme, document_id="1", first_name="Ana", last_name="Ruiz"
    )
    second = Employee.all_objects.create(
        organization=globex, document_id="1", first_name="Bruno", last_name="Díaz"
    )
    profile = ReaderProfile.all_objects.filter(organization=acme).first()
    profile.name = "Perfil ajustado"
    profile.save()
    credential = Credential.all_objects.create(
        organization=acme,
        employee=first,
        type=Credential.CredentialType.RFID,
        payload="0000AB12",
    )
    assert first.version > 0
    assert second.version > first.version
    assert profile.version > second.version
    assert credential.version > profile.version


def test_bulk_update_bumps_version(acme):
    employee = Employee.all_objects.create(
        organization=acme, document_id="1", first_name="Ana", last_name="Ruiz"
    )
    previous = employee.version
    employee.last_name = "Rueda"
    Employee.all_objects.bulk_update([employee], ["last_name"])
    employee.refresh_from_db()
    assert employee.version > previous
    assert employee.last_name == "Rueda"


def test_default_profiles_are_created_with_each_organization(acme):
    names = set(ReaderProfile.all_objects.filter(organization=acme).values_list("name", flat=True))
    assert "RFID hexadecimal 8 dígitos" in names
    assert "RFID decimal 10 dígitos" in names
    assert "ID numérico de lector de huella" in names


def test_viewer_can_preview_but_cannot_change_profiles(viewer_client, acme):
    profile = ReaderProfile.all_objects.get(organization=acme, name="RFID hexadecimal 8 dígitos")
    preview = viewer_client.post(
        f"/api/v1/reader-profiles/{profile.id}/preview/",
        {"sample": "  ab12  "},
        format="json",
    )
    assert preview.status_code == 200
    assert preview.data == {"ok": True, "payload": "0000AB12"}
    rejected = viewer_client.patch(
        f"/api/v1/reader-profiles/{profile.id}/",
        {"name": "Otro"},
        format="json",
    )
    assert rejected.status_code == 403


def test_preview_reports_normalization_errors(acme_client, acme):
    profile = ReaderProfile.all_objects.get(organization=acme, name="RFID hexadecimal 8 dígitos")
    preview = acme_client.post(
        f"/api/v1/reader-profiles/{profile.id}/preview/",
        {"sample": "ZZZZ", "normalization": [{"op": "regex_extract", "pattern": "([0-9]+)"}]},
        format="json",
    )
    assert preview.status_code == 200
    assert preview.data["ok"] is False


def test_node_api_key_is_shown_only_once(acme_client, operator_client):
    denied = operator_client.post(
        "/api/v1/nodes/",
        {"name": "Sede Sur", "timezone": "America/Bogota"},
        format="json",
    )
    assert denied.status_code == 403
    created = acme_client.post(
        "/api/v1/nodes/",
        {"name": "Sede Sur", "site": "Cali", "timezone": "America/Bogota"},
        format="json",
    )
    assert created.status_code == 201
    plain = created.data["api_key"]
    assert plain
    node = AccessNode.all_objects.get(pk=created.data["id"])
    assert node.api_key_hash == hash_secret(plain)
    assert "api_key_hash" not in created.data
    fetched = acme_client.get(f"/api/v1/nodes/{node.id}/")
    assert fetched.data["api_key"] is None
    rotated = acme_client.post(f"/api/v1/nodes/{node.id}/regenerate-key/")
    assert rotated.status_code == 200
    assert rotated.data["api_key"] not in (None, plain)
    node.refresh_from_db()
    assert node.api_key_hash == hash_secret(rotated.data["api_key"])


def test_reader_device_id_is_unique_per_node(operator_client, acme):
    node = AccessNode.all_objects.create(
        organization=acme,
        name="Sede",
        timezone="UTC",
        api_key_hash="a" * 64,
    )
    profile = ReaderProfile.all_objects.get(organization=acme, credential_type="FINGERPRINT")
    door = operator_client.post(
        "/api/v1/doors/",
        {
            "node": str(node.id),
            "name": "Portería",
            "relay_device_id": "COM4",
            "direction": "IN",
            "apb_mode": "HARD",
        },
        format="json",
    )
    assert door.status_code == 201
    other = Door.all_objects.create(
        organization=acme,
        node=node,
        name="Salida",
        relay_device_id="COM8",
        direction="OUT",
    )
    first = operator_client.post(
        "/api/v1/readers/",
        {
            "door": door.data["id"],
            "reader_profile": str(profile.id),
            "name": "Huella entrada",
            "reader_device_id": "COM3",
        },
        format="json",
    )
    assert first.status_code == 201
    duplicate = operator_client.post(
        "/api/v1/readers/",
        {
            "door": str(other.id),
            "reader_profile": str(profile.id),
            "name": "Huella salida",
            "reader_device_id": "COM3",
        },
        format="json",
    )
    assert duplicate.status_code == 400


def test_readers_can_be_listed_by_door(operator_client, acme_reader, acme_door):
    listed = operator_client.get(f"/api/v1/readers/?door={acme_door.id}")
    assert listed.status_code == 200
    assert str(acme_reader.id) in {row["id"] for row in listed.data["results"]}
    missing = operator_client.get("/api/v1/readers/?door=no-es-uuid")
    assert missing.status_code == 400


def test_versions_keep_growing_after_queryset_update(acme):
    employee = Employee.all_objects.create(
        organization=acme, document_id="8", first_name="Ana", last_name="Ruiz"
    )
    previous = employee.version
    Employee.all_objects.filter(pk=employee.pk).update(is_inside=True)
    employee.refresh_from_db()
    assert employee.is_inside is True
    assert employee.version > previous
