"""Aforo por sede y zona, y corrección de la presencia guardada."""

from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.access.models import (
    AccessAnomaly,
    AccessLog,
    AccessNode,
    AccessStatus,
    AnomalyKind,
    Direction,
    Zone,
)
from apps.people.models import Employee
from apps.sync.formatting import isoformat
from apps.sync.signals import occupancy_changed


@dataclass
class Presence:
    inside: bool
    at: object
    node_id: UUID | None
    zone_id: UUID | None
    log_id: UUID | None


def occupancy_snapshot(organization) -> dict:
    organization_id = getattr(organization, "pk", organization)
    inside = Employee.all_objects.filter(organization_id=organization_id, is_inside=True)
    counts = {
        row["presence_node_id"]: row["inside"]
        for row in inside.values("presence_node_id").annotate(inside=Count("id"))
    }
    zone_counts = {
        row["presence_zone_id"]: row["inside"]
        for row in inside.values("presence_zone_id").annotate(inside=Count("id"))
    }
    nodes = list(
        AccessNode.all_objects.filter(organization_id=organization_id, is_active=True).order_by(
            "name"
        )
    )
    known = {node.id for node in nodes}
    extra_ids = {node_id for node_id in counts if node_id is not None and node_id not in known}
    if extra_ids:
        nodes.extend(AccessNode.all_objects.filter(id__in=extra_ids).order_by("name"))
    sites = [
        {
            "node_id": str(node.id),
            "name": node.name,
            "site": node.site,
            "inside": counts.get(node.id, 0),
        }
        for node in nodes
    ]
    unassigned = counts.get(None, 0)
    if unassigned:
        sites.append({"node_id": None, "name": "Sin sede", "site": "", "inside": unassigned})

    zones = list(
        Zone.all_objects.filter(organization_id=organization_id, is_active=True).order_by("name")
    )
    known_zones = {zone.id for zone in zones}
    extra_zones = {
        zone_id for zone_id in zone_counts if zone_id is not None and zone_id not in known_zones
    }
    if extra_zones:
        zones.extend(Zone.all_objects.filter(id__in=extra_zones).order_by("name"))
    zone_rows = [
        {"zone_id": str(zone.id), "name": zone.name, "inside": zone_counts.get(zone.id, 0)}
        for zone in zones
    ]
    without_zone = zone_counts.get(None, 0)
    if without_zone:
        zone_rows.append({"zone_id": None, "name": "Sin zona", "inside": without_zone})
    return {
        "total_inside": inside.count(),
        "sites": sites,
        "zones": zone_rows,
    }


def reset_presence(organization, *, employee_id=None, node_id=None, actor_id=None) -> int:
    organization_id = organization.pk
    now = timezone.now()
    with transaction.atomic():
        if employee_id is not None:
            try:
                selected = Employee.all_objects.select_for_update().get(
                    pk=employee_id,
                    organization_id=organization_id,
                )
            except Employee.DoesNotExist as exc:
                raise NotFound("Empleado no encontrado.") from exc
            targets = [selected] if selected.is_inside else []
            scope = "employee"
            fallback_node = None
        else:
            node_exists = AccessNode.all_objects.filter(
                pk=node_id,
                organization_id=organization_id,
            ).exists()
            if not node_exists:
                raise NotFound("Nodo no encontrado.")
            targets = list(
                Employee.all_objects.select_for_update().filter(
                    organization_id=organization_id,
                    presence_node_id=node_id,
                    is_inside=True,
                )
            )
            scope = "node"
            fallback_node = node_id
        for employee in targets:
            previous_node = employee.presence_node_id
            previous_zone = employee.presence_zone_id
            employee.is_inside = False
            employee.presence_node_id = None
            employee.presence_zone_id = None
            employee.last_presence_at = now
            employee.presence_reset_at = now
            employee.save(
                update_fields=[
                    "is_inside",
                    "presence_node",
                    "presence_zone",
                    "last_presence_at",
                    "presence_reset_at",
                    "updated_at",
                ]
            )
            AccessAnomaly.all_objects.create(
                organization_id=organization_id,
                node_id=previous_node or fallback_node,
                employee=employee,
                kind=AnomalyKind.STATE_RESET,
                detail={
                    "actor_id": str(actor_id) if actor_id else None,
                    "scope": scope,
                    "previous_zone_id": str(previous_zone) if previous_zone else None,
                },
            )
        if targets:
            _notify(organization_id)
    return len(targets)


def reconcile_occupancy() -> int:
    from apps.tenants.models import Organization

    fixed = 0
    for organization_id in Organization.objects.filter(is_active=True).values_list("id", flat=True):
        fixed += reconcile_organization(organization_id)
    return fixed


def reconcile_organization(organization_id) -> int:
    fixed = 0
    employee_ids = Employee.all_objects.filter(organization_id=organization_id).values_list(
        "id",
        flat=True,
    )
    for employee_id in employee_ids:
        employee = Employee.all_objects.get(pk=employee_id)
        if _repair(employee):
            fixed += 1
    if fixed:
        _notify(organization_id)
    return fixed


def expected_presence(employee: Employee) -> Presence:
    logs = (
        AccessLog.all_objects.filter(employee=employee, status=AccessStatus.GRANTED)
        .select_related("door")
        .order_by("timestamp", "created_at")
    )
    if employee.presence_reset_at is not None:
        logs = logs.filter(timestamp__gt=employee.presence_reset_at)
    state = Presence(False, employee.presence_reset_at, None, None, None)
    for log in logs:
        inside = log.direction == Direction.IN
        zone_id = log.door.zone_id if inside and log.door_id and log.door is not None else None
        state = Presence(inside, log.timestamp, log.node_id, zone_id, log.id)
    return state


def _repair(employee: Employee) -> bool:
    expected = expected_presence(employee)
    if (
        employee.is_inside == expected.inside
        and employee.last_presence_at == expected.at
        and employee.presence_node_id == expected.node_id
        and employee.presence_zone_id == expected.zone_id
    ):
        return False
    before = _presence_detail(employee)
    employee.is_inside = expected.inside
    employee.last_presence_at = expected.at
    employee.presence_node_id = expected.node_id
    employee.presence_zone_id = expected.zone_id
    employee.save(
        update_fields=[
            "is_inside",
            "last_presence_at",
            "presence_node",
            "presence_zone",
            "updated_at",
        ]
    )
    AccessAnomaly.all_objects.create(
        organization_id=employee.organization_id,
        node_id=expected.node_id,
        access_log_id=expected.log_id,
        employee=employee,
        kind=AnomalyKind.OCCUPANCY_DRIFT,
        detail={"before": before, "after": _presence_detail(employee)},
    )
    return True


def _presence_detail(employee: Employee) -> dict:
    return {
        "is_inside": employee.is_inside,
        "last_presence_at": isoformat(employee.last_presence_at),
        "node_id": str(employee.presence_node_id) if employee.presence_node_id else None,
        "zone_id": str(employee.presence_zone_id) if employee.presence_zone_id else None,
    }


def _notify(organization_id) -> None:
    organization_key = str(organization_id)

    def emit(organization_id=organization_key):
        occupancy_changed.send(sender=Employee, organization_id=organization_id)

    connection = transaction.get_connection()
    if connection.in_atomic_block:
        transaction.on_commit(emit)
    else:
        emit()
