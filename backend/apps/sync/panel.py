from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import User
from apps.common.secrets import hash_secret
from apps.kiosk.models import Kiosk
from apps.sync.realtime import door_group, org_group
from apps.tenants.models import Membership, Organization


class DashboardConsumer(AsyncJsonWebsocketConsumer):
    """`ws/dashboard/`. El primer mensaje es `{"op": "auth", "token": "<jwt>"}`."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization_id = None

    async def connect(self):
        self.organization_id = None
        await self.accept()

    async def receive_json(self, content, **kwargs):
        operation = content.get("op")
        if self.organization_id is None:
            await self._authenticate(content, operation)
            return
        if operation == "ping":
            await self.send_json({"op": "pong"})
            return
        await self.send_json({"op": "error", "detail": "Operación no reconocida."})

    async def disconnect(self, code):
        if self.organization_id is None:
            return
        await self.channel_layer.group_discard(org_group(self.organization_id), self.channel_name)
        self.organization_id = None

    async def realtime_event(self, event):
        if self.organization_id is None:
            return
        await self.send_json(event["message"])

    async def _authenticate(self, content, operation):
        if operation != "auth":
            await self.send_json({"op": "error", "detail": "Se requiere autenticación."})
            await self.close(code=4001)
            return
        organization_id = await database_sync_to_async(resolve_panel_organization)(
            str(content.get("token") or "")
        )
        if organization_id is None:
            await self.send_json({"op": "error", "detail": "Token inválido."})
            await self.close(code=4001)
            return
        self.organization_id = organization_id
        await self.channel_layer.group_add(org_group(organization_id), self.channel_name)
        await self.send_json({"op": "auth_ok", "organization_id": organization_id})


class KioskConsumer(AsyncJsonWebsocketConsumer):
    """`ws/kiosk/`. Solo entra al grupo de la puerta del kiosco."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.group = None

    async def connect(self):
        self.group = None
        await self.accept()

    async def receive_json(self, content, **kwargs):
        operation = content.get("op")
        if self.group is None:
            await self._authenticate(content, operation)
            return
        if operation == "ping":
            await self.send_json({"op": "pong"})
            return
        await self.send_json({"op": "error", "detail": "Operación no reconocida."})

    async def disconnect(self, code):
        if self.group is None:
            return
        await self.channel_layer.group_discard(self.group, self.channel_name)
        self.group = None

    async def realtime_event(self, event):
        if self.group is None:
            return
        await self.send_json(event["message"])

    async def _authenticate(self, content, operation):
        if operation != "auth":
            await self.send_json({"op": "error", "detail": "Se requiere autenticación."})
            await self.close(code=4001)
            return
        identity = await database_sync_to_async(resolve_kiosk)(str(content.get("token") or ""))
        if identity is None:
            await self.send_json({"op": "error", "detail": "Token de kiosco inválido."})
            await self.close(code=4001)
            return
        self.group = door_group(identity["organization_id"], identity["door_id"])
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.send_json({"op": "auth_ok", **identity})


def resolve_panel_organization(token: str) -> str | None:
    if not token:
        return None
    try:
        access = AccessToken(token)
    except TokenError:
        return None
    user_id = access.get("user_id")
    organization_id = access.get("org_id")
    if not user_id or not organization_id:
        return None
    user = User.objects.filter(pk=user_id, is_active=True).first()
    organization = Organization.objects.filter(pk=organization_id, is_active=True).first()
    if user is None or organization is None:
        return None
    if (
        not user.is_superadmin
        and not Membership.objects.filter(
            user=user,
            organization=organization,
        ).exists()
    ):
        return None
    return str(organization.id)


def resolve_kiosk(token: str) -> dict | None:
    if not token:
        return None
    kiosk = (
        Kiosk.all_objects.select_related("door", "organization")
        .filter(
            kiosk_token_hash=hash_secret(token),
            is_active=True,
            organization__is_active=True,
        )
        .first()
    )
    if kiosk is None:
        return None
    now = timezone.now()
    Kiosk.all_objects.filter(pk=kiosk.pk).update(last_seen_at=now, updated_at=now)
    return {
        "kiosk_id": str(kiosk.id),
        "door_id": str(kiosk.door_id),
        "organization_id": str(kiosk.organization_id),
    }
