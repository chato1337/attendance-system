import uuid

from apps.sync.models import EnrollmentRead
from apps.sync.signals import enrollment_read_created


def test_node_reports_an_enrollment_read(node_client, acme_node, acme_reader):
    seen = []

    def remember(sender, read, node_id, **kwargs):
        seen.append((read.id, node_id))

    enrollment_read_created.connect(remember)
    try:
        created = node_client.post(
            "/api/v1/edge/enrollment-reads/",
            {
                "reader_id": str(acme_reader.id),
                "raw": "  ab12",
                "payload": "0000AB12",
                "credential_type": "RFID",
            },
            format="json",
        )
    finally:
        enrollment_read_created.disconnect(remember)
    assert created.status_code == 201
    stored = EnrollmentRead.all_objects.get(id=created.data["id"])
    assert stored.node_id == acme_node.id
    assert stored.reader_id == acme_reader.id
    assert stored.payload == "0000AB12"
    assert stored.organization_id == acme_node.organization_id
    assert seen == [(stored.id, acme_node.id)]


def test_panel_lists_enrollment_reads_for_its_organization(
    node_client, acme_client, globex_client, acme_reader
):
    created = node_client.post(
        "/api/v1/edge/enrollment-reads/",
        {
            "reader_id": str(acme_reader.id),
            "raw": "ab12",
            "payload": "AB12",
            "credential_type": "RFID",
        },
        format="json",
    )
    assert created.status_code == 201

    listed = acme_client.get("/api/v1/enrollment-reads/", {"reader": str(acme_reader.id)})
    assert listed.status_code == 200
    assert listed.data[0]["payload"] == "AB12"
    assert listed.data[0]["raw"] == "ab12"

    foreign = globex_client.get("/api/v1/enrollment-reads/")
    assert foreign.status_code == 200
    assert foreign.data == []

    invalid = acme_client.get("/api/v1/enrollment-reads/", {"reader": "no-es-uuid"})
    assert invalid.status_code == 400


def test_enrollment_read_rejects_a_foreign_reader(node_client):
    rejected = node_client.post(
        "/api/v1/edge/enrollment-reads/",
        {"reader_id": str(uuid.uuid4()), "raw": "AB12"},
        format="json",
    )
    assert rejected.status_code == 400
    assert EnrollmentRead.all_objects.count() == 0
