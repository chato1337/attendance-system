import uuid

from django.conf import settings
from django.db import connection
from django.utils import timezone

from apps.access.models import Door, Reader, ReaderProfile
from apps.people.models import Credential, Employee
from apps.sync.formatting import isoformat

# Puertas y lectores solo del nodo. El resto, de toda la organización.
# Reasignar una puerta a otro nodo exige un resync (`reload`) del nodo anterior:
# el delta incremental no emite una baja para el nodo que dejó de ser dueño.
_PAGE_SQL = """
SELECT id, version, kind FROM (
    SELECT id, version, 'employee' AS kind
    FROM people_employee
    WHERE organization_id = %s AND version > %s
    UNION ALL
    SELECT id, version, 'credential'
    FROM people_credential
    WHERE organization_id = %s AND version > %s
    UNION ALL
    SELECT id, version, 'reader_profile'
    FROM access_readerprofile
    WHERE organization_id = %s AND version > %s
    UNION ALL
    SELECT id, version, 'door'
    FROM access_door
    WHERE organization_id = %s AND node_id = %s AND version > %s
    UNION ALL
    SELECT r.id, r.version, 'reader'
    FROM access_reader r
    JOIN access_door d ON d.id = r.door_id
    WHERE r.organization_id = %s AND d.node_id = %s AND r.version > %s
) changes
ORDER BY version ASC
LIMIT %s
"""

_HEAD_SQL = """
SELECT COALESCE(MAX(version), 0) FROM (
    SELECT version FROM people_employee WHERE organization_id = %s
    UNION ALL
    SELECT version FROM people_credential WHERE organization_id = %s
    UNION ALL
    SELECT version FROM access_readerprofile WHERE organization_id = %s
    UNION ALL
    SELECT version FROM access_door WHERE organization_id = %s AND node_id = %s
    UNION ALL
    SELECT r.version
    FROM access_reader r
    JOIN access_door d ON d.id = r.door_id
    WHERE r.organization_id = %s AND d.node_id = %s
) visible
"""


def current_version(node) -> int:
    org_id = node.organization_id
    params = [org_id, org_id, org_id, org_id, node.pk, org_id, node.pk]
    with connection.cursor() as cursor:
        cursor.execute(_HEAD_SQL, params)
        row = cursor.fetchone()
    return int(row[0] or 0)


def _page_keys(node, since_version: int, limit: int) -> list[tuple]:
    org_id = node.organization_id
    params = [
        org_id,
        since_version,
        org_id,
        since_version,
        org_id,
        since_version,
        org_id,
        node.pk,
        since_version,
        org_id,
        node.pk,
        since_version,
        limit + 1,
    ]
    with connection.cursor() as cursor:
        cursor.execute(_PAGE_SQL, params)
        rows = []
        for row_id, version, kind in cursor.fetchall():
            rows.append((uuid.UUID(str(row_id)), int(version), kind))
        return rows


def _employee_row(employee: Employee) -> dict:
    return {
        "id": str(employee.id),
        "document_id": employee.document_id,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "department_id": str(employee.department_id) if employee.department_id else None,
        "is_active": employee.is_active,
        "is_inside": employee.is_inside,
        "version": employee.version,
    }


def _credential_row(credential: Credential) -> dict:
    return {
        "id": str(credential.id),
        "employee_id": str(credential.employee_id),
        "type": credential.type,
        "payload": credential.payload,
        "is_active": credential.is_active,
        "valid_from": isoformat(credential.valid_from),
        "valid_until": isoformat(credential.valid_until),
        "version": credential.version,
    }


def _profile_row(profile: ReaderProfile) -> dict:
    return {
        "id": str(profile.id),
        "name": profile.name,
        "credential_type": profile.credential_type,
        "normalization": profile.normalization,
        "min_length": profile.min_length,
        "max_length": profile.max_length,
        "is_active": profile.is_active,
        "version": profile.version,
    }


def _door_row(door: Door) -> dict:
    return {
        "id": str(door.id),
        "node_id": str(door.node_id),
        "zone_id": str(door.zone_id) if door.zone_id else None,
        "name": door.name,
        "relay_device_id": door.relay_device_id,
        "direction": door.direction,
        "apb_mode": door.apb_mode,
        "face_enabled": door.face_enabled,
        "required_factors": door.required_factors,
        "is_active": door.is_active,
        "version": door.version,
    }


def _reader_row(reader: Reader) -> dict:
    return {
        "id": str(reader.id),
        "door_id": str(reader.door_id),
        "reader_profile_id": str(reader.reader_profile_id),
        "name": reader.name,
        "reader_device_id": reader.reader_device_id,
        "is_active": reader.is_active,
        "version": reader.version,
    }


def build_delta(node, since_version: int, limit: int | None = None) -> dict:
    if limit is None:
        limit = settings.EDGE_DELTA_DEFAULT_LIMIT
    limit = max(1, min(int(limit), settings.EDGE_DELTA_MAX_LIMIT))
    head = current_version(node)
    keys = _page_keys(node, since_version, limit)
    has_more = len(keys) > limit
    page = keys[:limit]
    buckets: dict[str, list] = {
        "employee": [],
        "credential": [],
        "reader_profile": [],
        "door": [],
        "reader": [],
    }
    grouped: dict[str, list] = {kind: [] for kind in buckets}
    for row_id, _version, kind in page:
        grouped[kind].append(row_id)

    employees = {item.id: item for item in Employee.all_objects.filter(id__in=grouped["employee"])}
    credentials = {
        item.id: item for item in Credential.all_objects.filter(id__in=grouped["credential"])
    }
    profiles = {
        item.id: item for item in ReaderProfile.all_objects.filter(id__in=grouped["reader_profile"])
    }
    doors = {item.id: item for item in Door.all_objects.filter(id__in=grouped["door"])}
    readers = {item.id: item for item in Reader.all_objects.filter(id__in=grouped["reader"])}
    serializers = {
        "employee": (_employee_row, employees),
        "credential": (_credential_row, credentials),
        "reader_profile": (_profile_row, profiles),
        "door": (_door_row, doors),
        "reader": (_reader_row, readers),
    }
    for row_id, _version, kind in page:
        render, found = serializers[kind]
        item = found.get(row_id)
        if item is not None:
            buckets[kind].append(render(item))

    if page:
        next_since = int(page[-1][1])
    else:
        next_since = max(since_version, head)
    return {
        "server_time": isoformat(timezone.now()),
        "current_version": head,
        "next_since_version": next_since,
        "has_more": has_more,
        "employees": buckets["employee"],
        "credentials": buckets["credential"],
        "reader_profiles": buckets["reader_profile"],
        "doors": buckets["door"],
        "readers": buckets["reader"],
    }
