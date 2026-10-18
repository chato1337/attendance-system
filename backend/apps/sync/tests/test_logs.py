import uuid
from datetime import UTC, datetime

from django.test import TestCase

from apps.access.models import AccessAnomaly, AccessLog
from apps.people.models import Employee
from apps.sync.signals import access_log_created


def _log(**overrides):
    body = {
        "id": str(uuid.uuid4()),
        "timestamp": "2026-10-18T10:00:00Z",
        "direction": "IN",
        "status": "GRANTED",
        "method": "RFID",
        "source": "gateway",
    }
    body.update(overrides)
    return body


def _post(client, logs, node_id=None):
    body = {"logs": logs}
    if node_id is not None:
        body["node_id"] = str(node_id)
    return client.post("/api/v1/edge/logs/batch/", body, format="json")


def test_batch_updates_presence_and_ignores_duplicates_and_stale_events(
    node_client, acme_node, acme_employee, acme_door
):
    entered = _log(
        employee_id=str(acme_employee.id),
        door_id=str(acme_door.id),
        timestamp="2026-10-18T10:00:00Z",
    )
    created = _post(node_client, [entered])
    assert created.status_code == 200
    assert created.data["accepted"] == [entered["id"]]
    acme_employee.refresh_from_db()
    assert acme_employee.is_inside is True
    assert acme_employee.last_presence_at == datetime(2026, 10, 18, 10, 0, tzinfo=UTC)

    left = _log(
        employee_id=str(acme_employee.id),
        door_id=str(acme_door.id),
        timestamp="2026-10-18T18:00:00Z",
        direction="OUT",
    )
    stale = _log(
        employee_id=str(acme_employee.id),
        door_id=str(acme_door.id),
        timestamp="2026-10-18T09:00:00Z",
        direction="IN",
    )
    follow = _post(node_client, [left, stale])
    assert follow.status_code == 200
    assert set(follow.data["accepted"]) == {left["id"], stale["id"]}
    acme_employee.refresh_from_db()
    assert acme_employee.is_inside is False
    assert acme_employee.last_presence_at == datetime(2026, 10, 18, 18, 0, tzinfo=UTC)

    replay = _post(node_client, [entered, left])
    assert replay.data["accepted"] == []
    assert set(replay.data["duplicated"]) == {entered["id"], left["id"]}
    assert AccessLog.all_objects.filter(node=acme_node).count() == 3
    acme_employee.refresh_from_db()
    assert acme_employee.is_inside is False


def test_unknown_employee_is_stored_without_a_foreign_link(node_client, acme, globex, acme_door):
    foreign = Employee.all_objects.create(
        organization=globex,
        document_id="1",
        first_name="Otra",
        last_name="Org",
    )
    missing = _log(employee_id=str(uuid.uuid4()), door_id=str(acme_door.id))
    foreign_log = _log(employee_id=str(foreign.id), door_id=str(acme_door.id))
    response = _post(node_client, [missing, foreign_log])
    assert set(response.data["accepted"]) == {missing["id"], foreign_log["id"]}
    stored = AccessLog.all_objects.filter(id__in=[missing["id"], foreign_log["id"]])
    assert set(stored.values_list("employee_id", flat=True)) == {None}
    assert stored.filter(organization=acme).count() == 2


def test_unknown_door_is_rejected_and_invalid_rows_do_not_drop_the_batch(
    node_client, acme_node, acme_employee
):
    valid = _log(employee_id=str(acme_employee.id))
    unknown_door = _log(employee_id=str(acme_employee.id), door_id=str(uuid.uuid4()))
    broken = _log(timestamp="ayer", direction="SIDEWAYS")
    response = _post(node_client, [valid, unknown_door, broken])
    assert response.status_code == 200
    assert response.data["accepted"] == [valid["id"]]
    reasons = {item["reason"] for item in response.data["rejected"]}
    assert reasons == {"unknown_door", "invalid_timestamp"}
    mismatch = _post(node_client, [valid], node_id=uuid.uuid4())
    assert mismatch.status_code == 400
    matched = _post(node_client, [], node_id=acme_node.id)
    assert matched.status_code == 200


def test_denied_and_soft_apb_are_recorded(node_client, acme_employee, acme_door):
    denied = _log(
        employee_id=str(acme_employee.id),
        door_id=str(acme_door.id),
        status="DENIED",
        denial_reason="UNKNOWN_CREDENTIAL",
        timestamp="2026-10-18T11:00:00Z",
    )
    hard = _log(
        employee_id=str(acme_employee.id),
        door_id=str(acme_door.id),
        status="DENIED",
        denial_reason="APB_VIOLATION",
        timestamp="2026-10-18T11:05:00Z",
    )
    soft = _log(
        employee_id=str(acme_employee.id),
        door_id=str(acme_door.id),
        status="GRANTED",
        denial_reason="APB_VIOLATION",
        direction="OUT",
        timestamp="2026-10-18T11:10:00Z",
    )
    response = _post(node_client, [denied, hard, soft])
    assert len(response.data["accepted"]) == 3
    acme_employee.refresh_from_db()
    assert acme_employee.is_inside is False
    assert AccessAnomaly.all_objects.filter(employee=acme_employee).count() == 2


def test_batch_size_limit_and_signal(node_client, acme_employee):
    too_many = [_log() for _ in range(501)]
    assert _post(node_client, too_many).status_code == 400
    received = []

    def handler(sender, log, **kwargs):
        received.append(log.id)

    access_log_created.connect(handler)
    payload = _log(employee_id=str(acme_employee.id))
    try:
        with TestCase.captureOnCommitCallbacks(execute=True):
            assert _post(node_client, [payload]).status_code == 200
            assert _post(node_client, [payload]).data["duplicated"] == [payload["id"]]
    finally:
        access_log_created.disconnect(handler)
    assert received == [uuid.UUID(payload["id"])]


def test_in_batch_duplicate_is_not_inserted_twice(node_client, acme_node):
    payload = _log()
    response = _post(node_client, [payload, dict(payload)])
    assert response.data["accepted"] == [payload["id"]]
    assert response.data["duplicated"] == [payload["id"]]
    assert AccessLog.all_objects.filter(node=acme_node).count() == 1
