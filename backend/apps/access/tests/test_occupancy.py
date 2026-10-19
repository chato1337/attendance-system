import random
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.access.models import AccessAnomaly, AccessNode, AnomalyKind, Door, Zone
from apps.access.occupancy import occupancy_snapshot, reconcile_organization, reset_presence
from apps.common.secrets import generate_secret
from apps.people.models import Employee
from apps.sync.ingestion import ingest_logs


def _punch(node, employee, door, when, **overrides):
    body = {
        "id": str(uuid.uuid4()),
        "employee_id": str(employee.id),
        "door_id": str(door.id),
        "timestamp": when,
        "direction": door.direction,
        "status": "GRANTED",
        "method": "RFID",
        "source": "gateway",
    }
    body.update(overrides)
    return ingest_logs(node, [body])


def _node(organization, name):
    _plain, digest = generate_secret()
    return AccessNode.all_objects.create(
        organization=organization,
        name=name,
        site=name,
        api_key_hash=digest,
    )


def _door(organization, node, name, direction, zone=None):
    return Door.all_objects.create(
        organization=organization,
        node=node,
        zone=zone,
        name=name,
        relay_device_id=name,
        direction=direction,
    )


def test_snapshot_counts_inside_employees_by_site_and_zone(acme, acme_node, acme_employee):
    zone = Zone.all_objects.create(organization=acme, name="Planta")
    other = Employee.all_objects.create(
        organization=acme,
        document_id="901",
        first_name="Ana",
        last_name="Ruiz",
    )
    outside = Employee.all_objects.create(
        organization=acme,
        document_id="902",
        first_name="Luis",
        last_name="Paz",
    )
    entered = _door(acme, acme_node, "Ingreso", "IN", zone)
    _punch(acme_node, acme_employee, entered, "2026-10-18T08:00:00Z")
    _punch(acme_node, other, entered, "2026-10-18T08:05:00Z")
    _punch(acme_node, outside, entered, "2026-10-18T08:10:00Z")
    _punch(acme_node, outside, _door(acme, acme_node, "Salida", "OUT"), "2026-10-18T18:00:00Z")

    snapshot = occupancy_snapshot(acme)
    assert snapshot["total_inside"] == 2
    assert sum(site["inside"] for site in snapshot["sites"]) == 2
    site = next(item for item in snapshot["sites"] if item["node_id"] == str(acme_node.id))
    assert site["inside"] == 2
    zone_row = next(item for item in snapshot["zones"] if item["zone_id"] == str(zone.id))
    assert zone_row["inside"] == 2


def test_late_punch_from_another_node_does_not_revert_presence(acme, acme_node, acme_employee):
    zone = Zone.all_objects.create(organization=acme, name="Recepción")
    south = _node(acme, "Sede Sur")
    main = _door(acme, acme_node, "Principal", "IN", zone)
    back = _door(acme, south, "Trasera", "OUT")
    _punch(acme_node, acme_employee, main, "2026-10-18T12:00:00Z")
    _punch(south, acme_employee, back, "2026-10-18T11:00:00Z")

    acme_employee.refresh_from_db()
    assert acme_employee.is_inside is True
    assert acme_employee.presence_node_id == acme_node.id
    assert acme_employee.presence_zone_id == zone.id
    anomaly = AccessAnomaly.all_objects.get(employee=acme_employee, kind=AnomalyKind.APB_CONFLICT)
    assert anomaly.node_id == south.id
    assert anomaly.detail["resolution"] == "kept_newer"
    assert anomaly.detail["kept_inside"] is True


def test_newer_punch_from_another_node_wins_without_a_conflict(acme, acme_node, acme_employee):
    south = _node(acme, "Sede Sur")
    main = _door(acme, acme_node, "Principal", "IN")
    back = _door(acme, south, "Trasera", "OUT")
    _punch(acme_node, acme_employee, main, "2026-10-18T10:00:00Z")
    _punch(south, acme_employee, back, "2026-10-18T12:00:00Z")
    acme_employee.refresh_from_db()
    assert acme_employee.is_inside is False
    assert acme_employee.presence_node_id == south.id
    assert not AccessAnomaly.all_objects.filter(kind=AnomalyKind.APB_CONFLICT).exists()


def test_reset_clears_presence_and_ignores_older_punches(
    acme, acme_node, acme_employee, acme_admin
):
    door = _door(acme, acme_node, "Principal", "IN")
    _punch(acme_node, acme_employee, door, "2026-10-18T08:00:00Z")
    reset = reset_presence(acme, employee_id=acme_employee.id, actor_id=acme_admin.id)
    assert reset == 1
    acme_employee.refresh_from_db()
    assert acme_employee.is_inside is False
    assert acme_employee.presence_reset_at is not None
    assert AccessAnomaly.all_objects.filter(kind=AnomalyKind.STATE_RESET).count() == 1

    _punch(acme_node, acme_employee, door, "2026-10-18T07:00:00Z")
    acme_employee.refresh_from_db()
    assert acme_employee.is_inside is False

    later = (timezone.now() + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    _punch(acme_node, acme_employee, door, later)
    acme_employee.refresh_from_db()
    assert acme_employee.is_inside is True
    assert reconcile_organization(acme.id) == 0


def test_reset_by_node_only_clears_that_site(acme, acme_node, acme_employee):
    south = _node(acme, "Sede Sur")
    other = Employee.all_objects.create(
        organization=acme,
        document_id="901",
        first_name="Ana",
        last_name="Ruiz",
    )
    north_door = _door(acme, acme_node, "Norte", "IN")
    south_door = _door(acme, south, "Sur", "IN")
    _punch(acme_node, acme_employee, north_door, "2026-10-18T08:00:00Z")
    _punch(south, other, south_door, "2026-10-18T08:00:00Z")
    assert reset_presence(acme, node_id=acme_node.id) == 1
    acme_employee.refresh_from_db()
    other.refresh_from_db()
    assert acme_employee.is_inside is False
    assert other.is_inside is True


def test_reconcile_repairs_drift_and_respects_a_reset(acme, acme_node, acme_employee):
    door = _door(acme, acme_node, "Principal", "IN")
    Employee.all_objects.filter(pk=acme_employee.pk).update(is_inside=True)
    assert reconcile_organization(acme.id) == 1
    acme_employee.refresh_from_db()
    assert acme_employee.is_inside is False
    assert AccessAnomaly.all_objects.filter(kind=AnomalyKind.OCCUPANCY_DRIFT).count() == 1

    _punch(acme_node, acme_employee, door, "2026-10-18T08:00:00Z")
    reset_presence(acme, employee_id=acme_employee.id)
    Employee.all_objects.filter(pk=acme_employee.pk).update(is_inside=True)
    assert reconcile_organization(acme.id) == 1
    acme_employee.refresh_from_db()
    assert acme_employee.is_inside is False


def test_one_thousand_random_punches_match_the_stored_state(acme, acme_node):
    zone_a = Zone.all_objects.create(organization=acme, name="A")
    zone_b = Zone.all_objects.create(organization=acme, name="B")
    south = _node(acme, "Sede Sur")
    doors = [
        _door(acme, acme_node, "Norte IN", "IN", zone_a),
        _door(acme, south, "Sur IN", "IN", zone_b),
        _door(acme, acme_node, "Norte OUT", "OUT"),
    ]
    employees = [
        Employee.all_objects.create(
            organization=acme,
            document_id=str(1000 + index),
            first_name="Empleado",
            last_name=str(index),
        )
        for index in range(20)
    ]
    rng = random.Random(18)
    start = datetime(2026, 6, 1, tzinfo=UTC)
    for index in range(1000):
        door = rng.choice(doors)
        when = (start + timedelta(seconds=index)).isoformat().replace("+00:00", "Z")
        result = _punch(door.node, rng.choice(employees), door, when)
        assert result["rejected"] == []

    inside = Employee.all_objects.filter(organization=acme, is_inside=True)
    snapshot = occupancy_snapshot(acme)
    assert snapshot["total_inside"] == inside.count()
    assert sum(site["inside"] for site in snapshot["sites"]) == snapshot["total_inside"]
    assert sum(zone["inside"] for zone in snapshot["zones"]) == snapshot["total_inside"]
    assert reconcile_organization(acme.id) == 0


def test_occupancy_api_is_isolated_and_reset_requires_an_operator(
    acme_client, viewer_client, globex_client, acme, acme_node, acme_employee, globex
):
    door = _door(acme, acme_node, "Principal", "IN")
    _punch(acme_node, acme_employee, door, "2026-10-18T08:00:00Z")
    foreign = Employee.all_objects.create(
        organization=globex,
        document_id="1",
        first_name="Otra",
        last_name="Org",
        is_inside=True,
    )

    own = acme_client.get("/api/v1/occupancy/")
    assert own.status_code == 200
    assert own.data["total_inside"] == 1
    assert viewer_client.get("/api/v1/occupancy/").status_code == 200
    other = globex_client.get("/api/v1/occupancy/")
    assert other.status_code == 200
    assert other.data["total_inside"] == 1
    assert all(site["name"] != acme_node.name for site in other.data["sites"])

    forbidden = viewer_client.post(
        "/api/v1/occupancy/reset/",
        {"employee": str(acme_employee.id)},
        format="json",
    )
    assert forbidden.status_code == 403
    missing = acme_client.post("/api/v1/occupancy/reset/", {}, format="json")
    assert missing.status_code == 400
    both = acme_client.post(
        "/api/v1/occupancy/reset/",
        {"employee": str(acme_employee.id), "node": str(acme_node.id)},
        format="json",
    )
    assert both.status_code == 400
    foreign_reset = acme_client.post(
        "/api/v1/occupancy/reset/",
        {"employee": str(foreign.id)},
        format="json",
    )
    assert foreign_reset.status_code == 404
    cleared = acme_client.post(
        "/api/v1/occupancy/reset/",
        {"node": str(acme_node.id)},
        format="json",
    )
    assert cleared.status_code == 200
    assert cleared.data["reset"] == 1
    acme_employee.refresh_from_db()
    assert acme_employee.is_inside is False
    foreign.refresh_from_db()
    assert foreign.is_inside is True
    assert acme_client.get("/api/v1/access-anomalies/").data["count"] == 1
    assert globex_client.get("/api/v1/access-anomalies/").data["count"] == 0


def test_nightly_reconcile_task_runs(acme):
    from apps.access.tasks import reconcile_occupancy_task

    assert reconcile_occupancy_task() == 0


def test_unknown_reset_target_raises_not_found(acme):
    with pytest.raises(NotFound):
        reset_presence(acme, node_id=uuid.uuid4())
