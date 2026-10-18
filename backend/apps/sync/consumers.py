from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.access.models import AccessNode
from apps.sync.authentication import resolve_node
from apps.sync.commands import (
    CommandExpired,
    CommandValidationError,
    acknowledge,
    claim_command,
    claim_pending,
    command_body,
    group_name,
)
from apps.sync.models import EdgeCommand


class EdgeConsumer(AsyncJsonWebsocketConsumer):
    """Canal `ws/edge/`. El primer mensaje debe ser `{"op": "auth", "token": "..."}`."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.node_id = None

    async def connect(self):
        self.node_id = None
        await self.accept()

    async def receive_json(self, content, **kwargs):
        operation = content.get("op")
        if self.node_id is None:
            await self._authenticate(content, operation)
            return
        if operation == "ack":
            await self._ack(content)
            return
        if operation == "ping":
            await self.send_json({"op": "pong"})
            return
        await self.send_json({"op": "error", "detail": "Operación no reconocida."})

    async def disconnect(self, code):
        if self.node_id is None:
            return
        await self.channel_layer.group_discard(group_name(self.node_id), self.channel_name)
        await database_sync_to_async(set_commands_connected)(self.node_id, False)
        self.node_id = None

    async def edge_command(self, event):
        if self.node_id is None:
            return
        command = await database_sync_to_async(claim_command)(event["command_id"], self.node_id)
        if command is None:
            return
        await self.send_json({"op": "command", **command_body(command)})

    async def _authenticate(self, content, operation):
        if operation != "auth":
            await self.send_json({"op": "error", "detail": "Se requiere autenticación."})
            await self.close(code=4001)
            return
        node = await database_sync_to_async(resolve_node)(str(content.get("token") or ""))
        if node is None:
            await self.send_json({"op": "error", "detail": "API key de nodo inválida."})
            await self.close(code=4001)
            return
        self.node_id = str(node.pk)
        await self.channel_layer.group_add(group_name(self.node_id), self.channel_name)
        await database_sync_to_async(set_commands_connected)(node.pk, True)
        await self.send_json({"op": "auth_ok", "node_id": self.node_id})
        pending = await database_sync_to_async(claim_pending)(node)
        for command in pending:
            await self.send_json({"op": "command", **command_body(command)})

    async def _ack(self, content):
        try:
            command = await database_sync_to_async(acknowledge_for_node)(
                self.node_id,
                content.get("id"),
                content.get("result"),
            )
        except (EdgeCommand.DoesNotExist, DjangoValidationError, ValueError):
            await self.send_json({"op": "error", "detail": "No encontrado."})
            return
        except CommandExpired:
            await self.send_json({"op": "error", "detail": "El comando expiró."})
            return
        except CommandValidationError as exc:
            await self.send_json({"op": "error", "detail": exc.detail})
            return
        await self.send_json({"op": "ack_ok", "id": str(command.id), "status": command.status})


def set_commands_connected(node_id, connected: bool) -> None:
    AccessNode.all_objects.filter(pk=node_id).update(commands_connected=connected)


def acknowledge_for_node(node_id, command_id, result) -> EdgeCommand:
    node = AccessNode.all_objects.get(pk=node_id)
    return acknowledge(node, command_id, result)
