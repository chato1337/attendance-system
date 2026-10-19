import time
import uuid
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.access.models import Door, Reader
from apps.people.models import Credential
from apps.sync.formatting import isoformat
from apps.sync.models import EdgeCommand
from apps.sync.notify import command_subscription, notify_ack, notify_commands, wait_for_ack
from apps.sync.signals import command_settled

TERMINAL = {EdgeCommand.Status.ACKED, EdgeCommand.Status.FAILED, EdgeCommand.Status.EXPIRED}
OPEN = {EdgeCommand.Status.PENDING, EdgeCommand.Status.SENT}


class CommandValidationError(Exception):
    def __init__(self, detail):
        self.detail = detail
        super().__init__(detail)


class CommandExpired(Exception):
    def __init__(self, command: EdgeCommand):
        self.command = command
        super().__init__("expired")


def group_name(node_id) -> str:
    return f"edge.node.{node_id}"


def command_body(command: EdgeCommand) -> dict:
    return {
        "id": str(command.id),
        "type": command.type,
        "payload": command.payload,
        "status": command.status,
        "expires_at": isoformat(command.expires_at),
        "result": command.result,
        "created_at": isoformat(command.created_at),
        "sent_at": isoformat(command.sent_at),
        "acked_at": isoformat(command.acked_at),
    }


def expire_due_commands(node=None) -> int:
    queryset = EdgeCommand.all_objects.filter(status__in=OPEN, expires_at__lte=timezone.now())
    if node is not None:
        queryset = queryset.filter(node=node)
    return queryset.update(status=EdgeCommand.Status.EXPIRED)


def dispatch_command(
    node,
    command_type: str,
    payload: dict,
    *,
    timeout: float | None = None,
) -> EdgeCommand:
    if not node.is_active:
        raise CommandValidationError("El nodo está inactivo.")
    payload = validate_payload(node, command_type, payload)
    ttl = settings.EDGE_COMMAND_TTL_SECONDS[command_type]
    with transaction.atomic():
        command = EdgeCommand.all_objects.create(
            organization=node.organization,
            node=node,
            type=command_type,
            payload=payload,
            status=EdgeCommand.Status.PENDING,
            expires_at=timezone.now() + timedelta(seconds=ttl),
        )
        command_id = command.id
        node_id = node.pk
        transaction.on_commit(lambda: publish(command_id, node_id))
    if timeout and timeout > 0:
        _wait_until_settled(command_id, timeout)
    command.refresh_from_db()
    return command


def publish(command_id, node_id) -> None:
    notify_commands(node_id)
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        group_name(node_id),
        {"type": "edge.command", "command_id": str(command_id)},
    )


def poll_commands(node, wait: float) -> list[EdgeCommand]:
    wait = max(0.0, min(float(wait), settings.EDGE_COMMAND_POLL_MAX_WAIT))
    deadline = time.monotonic() + wait
    with command_subscription(node.pk) as event:
        while True:
            event.clear()
            claimed = claim_pending(node)
            if claimed or time.monotonic() >= deadline:
                return claimed
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return []
            event.wait(remaining)


def claim_pending(node) -> list[EdgeCommand]:
    expire_due_commands(node)
    now = timezone.now()
    with transaction.atomic():
        commands = list(
            EdgeCommand.all_objects.select_for_update(skip_locked=True)
            .filter(node=node, status=EdgeCommand.Status.PENDING, expires_at__gt=now)
            .order_by("created_at")
        )
        if not commands:
            return []
        sent_at = timezone.now()
        EdgeCommand.all_objects.filter(id__in=[item.id for item in commands]).update(
            status=EdgeCommand.Status.SENT,
            sent_at=sent_at,
        )
        for command in commands:
            command.status = EdgeCommand.Status.SENT
            command.sent_at = sent_at
        return commands


def claim_command(command_id, node_id) -> EdgeCommand | None:
    expire_due_commands()
    now = timezone.now()
    with transaction.atomic():
        command = (
            EdgeCommand.all_objects.select_for_update(skip_locked=True)
            .filter(
                pk=command_id,
                node_id=node_id,
                status=EdgeCommand.Status.PENDING,
                expires_at__gt=now,
            )
            .first()
        )
        if command is None:
            return None
        command.status = EdgeCommand.Status.SENT
        command.sent_at = timezone.now()
        command.save(update_fields=["status", "sent_at"])
        return command


def acknowledge(node, command_id, result: dict) -> EdgeCommand:
    if not isinstance(result, dict):
        raise CommandValidationError("result debe ser un objeto.")
    with transaction.atomic():
        try:
            command = EdgeCommand.all_objects.select_for_update().get(pk=command_id, node=node)
        except EdgeCommand.DoesNotExist as exc:
            raise EdgeCommand.DoesNotExist from exc
        if command.status in {EdgeCommand.Status.ACKED, EdgeCommand.Status.FAILED}:
            return command
        if command.status == EdgeCommand.Status.EXPIRED or command.expires_at <= timezone.now():
            if command.status != EdgeCommand.Status.EXPIRED:
                command.status = EdgeCommand.Status.EXPIRED
                command.save(update_fields=["status"])
            raise CommandExpired(command)
        command.status = _status_from_result(result)
        command.result = result
        command.acked_at = timezone.now()
        command.save(update_fields=["status", "result", "acked_at"])
        command_id = command.id
        transaction.on_commit(
            lambda: command_settled.send(sender=EdgeCommand, command_id=command_id)
        )
    notify_ack(command.id)
    return command


def validate_payload(node, command_type: str, payload) -> dict:
    if command_type not in EdgeCommand.Type.values:
        raise CommandValidationError("Tipo de comando no soportado.")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise CommandValidationError("payload debe ser un objeto.")
    if command_type == EdgeCommand.Type.IDENTIFICATION:
        door = _door(node, payload.get("door_id"))
        credential_type = payload.get("type")
        if credential_type not in Credential.CredentialType.values:
            raise CommandValidationError("type de identificación no es válido.")
        body = payload.get("payload")
        if not isinstance(body, str) or not body.strip():
            raise CommandValidationError("payload de identificación es obligatorio.")
        request_id = _uuid(payload.get("request_id"), "request_id")
        return {
            "door_id": str(door.id),
            "type": credential_type,
            "payload": body.strip(),
            "request_id": str(request_id),
        }
    if command_type == EdgeCommand.Type.OPEN_DOOR:
        door = _door(node, payload.get("door_id"))
        reason = _text(payload.get("reason"), "reason")
        actor = _text(payload.get("actor"), "actor")
        return {"door_id": str(door.id), "reason": reason, "actor": actor}
    if command_type == EdgeCommand.Type.ENROLLMENT_MODE:
        reader = _reader(node, payload.get("reader_id"))
        seconds = payload.get("seconds")
        if isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= 600:
            raise CommandValidationError("seconds debe ser un entero entre 1 y 600.")
        return {"reader_id": str(reader.id), "seconds": seconds}
    return {}


def _door(node, value) -> Door:
    door_id = _uuid(value, "door_id")
    door = Door.all_objects.filter(pk=door_id, node=node, organization=node.organization).first()
    if door is None:
        raise CommandValidationError("La puerta no pertenece al nodo.")
    return door


def _reader(node, value) -> Reader:
    reader_id = _uuid(value, "reader_id")
    reader = (
        Reader.all_objects.select_related("door")
        .filter(pk=reader_id, organization=node.organization, door__node=node)
        .first()
    )
    if reader is None:
        raise CommandValidationError("El lector no pertenece al nodo.")
    return reader


def _uuid(value, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise CommandValidationError(f"{field} debe ser un UUID.") from exc


def _text(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CommandValidationError(f"{field} es obligatorio.")
    return value.strip()


def _status_from_result(result: dict) -> str:
    status = str(result.get("status", "")).upper()
    if status in {"FAILED", "ERROR"}:
        return EdgeCommand.Status.FAILED
    return EdgeCommand.Status.ACKED


def _wait_until_settled(command_id, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        command = EdgeCommand.all_objects.filter(pk=command_id).only("status", "expires_at").first()
        if command is None or command.status in TERMINAL:
            return
        if command.expires_at <= timezone.now():
            expire_due_commands()
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        wait_for_ack(command_id, min(remaining, 0.2))
