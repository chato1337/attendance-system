from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.access.models import AccessNode
from apps.sync.formatting import isoformat
from apps.sync.signals import device_status_changed


def record_heartbeat(node: AccessNode, data: dict) -> dict:
    was_online = node.is_online
    now = timezone.now()
    node.last_heartbeat_at = now
    node.is_online = True
    node.agent_version = data.get("agent_version") or ""
    node.gateway_connected = bool(data["gateway_connected"])
    node.listening_devices = list(data.get("listening_devices") or [])
    node.queue_size = data["queue_size"]
    node.last_sync_version = data["last_version"]
    node.commands_connected = bool(data["commands_connected"])
    gateway_version = data.get("gateway_version")
    if gateway_version:
        node.gateway_version_reported = gateway_version
    node.save(
        update_fields=[
            "last_heartbeat_at",
            "is_online",
            "agent_version",
            "gateway_connected",
            "listening_devices",
            "queue_size",
            "last_sync_version",
            "commands_connected",
            "gateway_version_reported",
            "updated_at",
        ]
    )
    if not was_online:
        device_status_changed.send(sender=AccessNode, node=node, is_online=True)
    return {
        "server_time": isoformat(now),
        "is_online": True,
        "last_heartbeat_at": isoformat(now),
    }


def mark_stale_nodes_offline() -> int:
    cutoff = timezone.now() - timedelta(minutes=settings.EDGE_HEARTBEAT_TIMEOUT_MINUTES)
    stale = AccessNode.all_objects.filter(is_online=True).filter(
        Q(last_heartbeat_at__lt=cutoff) | Q(last_heartbeat_at__isnull=True)
    )
    count = 0
    for node in stale:
        node.is_online = False
        node.commands_connected = False
        node.save(update_fields=["is_online", "commands_connected", "updated_at"])
        device_status_changed.send(sender=AccessNode, node=node, is_online=False)
        count += 1
    return count
