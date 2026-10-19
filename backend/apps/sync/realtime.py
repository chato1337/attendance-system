"""Publica eventos del panel en grupos aislados por organización.

Los nombres de grupo usan puntos (`org.<id>`) porque el canal de Channels
no acepta dos puntos. El concepto del plan sigue siendo `org:<id>`.
"""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from apps.access.models import AccessStatus
from apps.access.occupancy import occupancy_snapshot
from apps.sync.formatting import isoformat
from apps.sync.models import EdgeCommand
from apps.sync.signals import (
    access_log_created,
    command_settled,
    device_status_changed,
    enrollment_read_created,
    occupancy_changed,
)

logger = logging.getLogger(__name__)


def org_group(organization_id) -> str:
    return f"org.{organization_id}"


def node_group(organization_id, node_id) -> str:
    return f"org.{organization_id}.node.{node_id}"


def door_group(organization_id, door_id) -> str:
    return f"org.{organization_id}.door.{door_id}"


def publish_event(organization_id, event: str, data: dict, *, node_id=None, door_id=None) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    message = {
        "event": event,
        "organization_id": str(organization_id),
        "occurred_at": isoformat(timezone.now()),
        "data": data,
    }
    groups = [org_group(organization_id)]
    if node_id is not None:
        groups.append(node_group(organization_id, node_id))
    if door_id is not None:
        groups.append(door_group(organization_id, door_id))
    payload = {"type": "realtime.event", "message": message}
    try:
        for group in groups:
            async_to_sync(layer.group_send)(group, payload)
    except Exception:
        logger.exception("No se pudo publicar el evento %s", event)


def connect_receivers() -> None:
    access_log_created.connect(_on_access_log, dispatch_uid="realtime.access_log")
    occupancy_changed.connect(_on_occupancy, dispatch_uid="realtime.occupancy")
    device_status_changed.connect(_on_device, dispatch_uid="realtime.device")
    enrollment_read_created.connect(_on_enrollment, dispatch_uid="realtime.enrollment")
    command_settled.connect(_on_command, dispatch_uid="realtime.command")


def _on_access_log(sender, log, **kwargs):
    event = "access.granted" if log.status == AccessStatus.GRANTED else "access.denied"
    publish_event(
        log.organization_id,
        event,
        {
            "id": str(log.id),
            "node_id": str(log.node_id),
            "door_id": str(log.door_id) if log.door_id else None,
            "employee_id": str(log.employee_id) if log.employee_id else None,
            "timestamp": isoformat(log.timestamp),
            "direction": log.direction,
            "status": log.status,
            "denial_reason": log.denial_reason,
            "method": log.method,
            "source": log.source,
        },
        node_id=log.node_id,
        door_id=log.door_id,
    )


def _on_occupancy(sender, organization_id, **kwargs):
    publish_event(organization_id, "occupancy.changed", occupancy_snapshot(organization_id))


def _on_device(sender, node, is_online, **kwargs):
    event = "node.online" if is_online else "node.offline"
    publish_event(
        node.organization_id,
        event,
        {
            "node_id": str(node.id),
            "name": node.name,
            "site": node.site,
            "is_online": bool(is_online),
            "agent_version": node.agent_version,
            "queue_size": node.queue_size,
            "commands_connected": node.commands_connected,
            "gateway_connected": node.gateway_connected,
            "last_heartbeat_at": isoformat(node.last_heartbeat_at),
        },
        node_id=node.id,
    )


def _on_enrollment(sender, read, **kwargs):
    door_id = None
    if read.reader_id and getattr(read, "reader", None) is not None:
        door_id = read.reader.door_id
    publish_event(
        read.organization_id,
        "enrollment.read",
        {
            "id": str(read.id),
            "node_id": str(read.node_id),
            "reader_id": str(read.reader_id) if read.reader_id else None,
            "door_id": str(door_id) if door_id else None,
            "raw": read.raw,
            "payload": read.payload,
            "credential_type": read.credential_type,
            "error": read.error,
        },
        node_id=read.node_id,
        door_id=door_id,
    )


def _on_command(sender, command_id, **kwargs):
    command = EdgeCommand.all_objects.filter(pk=command_id).first()
    if command is None:
        return
    door_id = None
    if isinstance(command.payload, dict) and command.payload.get("door_id"):
        door_id = command.payload["door_id"]
    publish_event(
        command.organization_id,
        "command.acked",
        {
            "id": str(command.id),
            "node_id": str(command.node_id),
            "type": command.type,
            "status": command.status,
            "payload": command.payload,
            "result": command.result,
        },
        node_id=command.node_id,
        door_id=door_id,
    )
