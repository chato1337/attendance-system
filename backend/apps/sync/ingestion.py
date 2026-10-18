import uuid
from collections import defaultdict

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.access.models import (
    AccessAnomaly,
    AccessLog,
    AccessMethod,
    AccessSource,
    AccessStatus,
    AnomalyKind,
    DenialReason,
    Direction,
    Door,
)
from apps.people.models import Credential, Employee
from apps.sync.formatting import isoformat
from apps.sync.signals import access_log_created

_OPTIONAL_UUID = ("employee_id", "credential_id", "door_id")


def ingest_logs(node, raw_logs: list[dict]) -> dict:
    rejected: list[dict] = []
    duplicated: list[str] = []
    parsed: list[dict] = []
    seen: set[uuid.UUID] = set()

    for raw in raw_logs:
        item, error = _parse_log(raw)
        if error:
            rejected.append({"id": _raw_id(raw), "reason": error})
            continue
        if item["id"] in seen:
            duplicated.append(str(item["id"]))
            continue
        seen.add(item["id"])
        parsed.append(item)

    existing = set(AccessLog.all_objects.filter(id__in=seen).values_list("id", flat=True))
    fresh = []
    for item in parsed:
        if item["id"] in existing:
            duplicated.append(str(item["id"]))
        else:
            fresh.append(item)

    door_ids = {item["door_id"] for item in fresh if item["door_id"]}
    doors = {
        door.id: door
        for door in Door.all_objects.filter(
            id__in=door_ids,
            node=node,
            organization=node.organization,
        )
    }
    accepted: list[AccessLog] = []
    with transaction.atomic():
        for index, item in enumerate(fresh):
            if item["door_id"] and item["door_id"] not in doors:
                rejected.append({"id": str(item["id"]), "reason": "unknown_door"})
                continue
            employee = _same_org(Employee, node, item["employee_id"])
            credential = _same_org(Credential, node, item["credential_id"])
            try:
                with transaction.atomic():
                    log = AccessLog.all_objects.create(
                        id=item["id"],
                        organization=node.organization,
                        node=node,
                        door_id=item["door_id"] if item["door_id"] in doors else None,
                        employee=employee,
                        credential=credential,
                        timestamp=item["timestamp"],
                        direction=item["direction"],
                        status=item["status"],
                        denial_reason=item["denial_reason"],
                        method=item["method"],
                        source=item["source"],
                    )
            except IntegrityError:
                duplicated.append(str(item["id"]))
                continue
            log.batch_index = index
            accepted.append(log)
            if log.denial_reason == DenialReason.APB_VIOLATION:
                AccessAnomaly.all_objects.create(
                    organization=node.organization,
                    node=node,
                    access_log=log,
                    employee=employee,
                    kind=AnomalyKind.APB_REPORTED,
                    detail={
                        "status": log.status,
                        "direction": log.direction,
                        "denial_reason": log.denial_reason,
                    },
                )
        _apply_presence(accepted)
        created_ids = [log.id for log in accepted]

        def emit(log_ids=created_ids):
            logs = AccessLog.all_objects.filter(id__in=log_ids)
            for log in logs:
                access_log_created.send(sender=AccessLog, log=log, node_id=node.pk)

        transaction.on_commit(emit)

    return {
        "server_time": isoformat(timezone.now()),
        "accepted": [str(log.id) for log in accepted],
        "duplicated": duplicated,
        "rejected": rejected,
    }


def _apply_presence(logs: list[AccessLog]) -> None:
    grouped: dict = defaultdict(list)
    for log in logs:
        if log.employee_id and log.status == AccessStatus.GRANTED:
            grouped[log.employee_id].append(log)
    for employee_id, events in grouped.items():
        try:
            employee = Employee.all_objects.select_for_update().get(pk=employee_id)
        except Employee.DoesNotExist:
            continue
        ordered = sorted(events, key=lambda item: (item.timestamp, item.batch_index))
        changed = False
        for event in ordered:
            presence_at = employee.last_presence_at
            if presence_at is not None and event.timestamp < presence_at:
                continue
            inside = event.direction == Direction.IN
            if employee.is_inside != inside or employee.last_presence_at != event.timestamp:
                employee.is_inside = inside
                employee.last_presence_at = event.timestamp
                changed = True
        if changed:
            employee.save(update_fields=["is_inside", "last_presence_at", "updated_at"])


def _same_org(model, node, object_id):
    if object_id is None:
        return None
    return model.all_objects.filter(pk=object_id, organization=node.organization).first()


def _raw_id(raw) -> str | None:
    if not isinstance(raw, dict):
        return None
    value = raw.get("id")
    if value in (None, ""):
        return None
    return str(value)


def _parse_log(raw) -> tuple[dict | None, str | None]:
    if not isinstance(raw, dict):
        return None, "invalid_body"
    try:
        log_id = uuid.UUID(str(raw.get("id")))
    except (TypeError, ValueError):
        return None, "invalid_id"
    timestamp = parse_datetime(str(raw.get("timestamp") or ""))
    if timestamp is None or timezone.is_naive(timestamp):
        return None, "invalid_timestamp"
    direction = raw.get("direction")
    if direction not in Direction.values:
        return None, "invalid_direction"
    status = raw.get("status")
    if status not in AccessStatus.values:
        return None, "invalid_status"
    denial = raw.get("denial_reason") or ""
    if denial and denial not in DenialReason.values:
        return None, "invalid_denial_reason"
    method = raw.get("method") or ""
    if method and method not in AccessMethod.values:
        return None, "invalid_method"
    source = raw.get("source") or ""
    if source and source not in AccessSource.values:
        return None, "invalid_source"
    refs = {}
    for field in _OPTIONAL_UUID:
        value = raw.get(field)
        if value in (None, ""):
            refs[field] = None
            continue
        try:
            refs[field] = uuid.UUID(str(value))
        except (TypeError, ValueError):
            return None, f"invalid_{field}"
    return {
        "id": log_id,
        "timestamp": timestamp,
        "direction": direction,
        "status": status,
        "denial_reason": denial,
        "method": method,
        "source": source,
        **refs,
    }, None
