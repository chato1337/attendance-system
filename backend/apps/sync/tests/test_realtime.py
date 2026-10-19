import asyncio
import uuid
from datetime import timedelta

import pytest
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import connections
from django.test import TestCase
from django.utils import timezone

from apps.access.models import Door
from apps.accounts.tokens import issue_tokens
from apps.common.secrets import generate_secret
from apps.kiosk.models import Kiosk
from apps.sync.commands import acknowledge, dispatch_command
from apps.sync.heartbeat import mark_stale_nodes_offline, record_heartbeat
from apps.sync.ingestion import ingest_logs
from apps.sync.realtime import door_group, org_group, publish_event


def _drain(layer, channel, limit=6):
    found = []

    async def take():
        return await asyncio.wait_for(layer.receive(channel), 0.2)

    for _ in range(limit):
        try:
            found.append(async_to_sync(take)())
        except TimeoutError:
            break
    return [item["message"] for item in found]


def _listen(organization_id):
    layer = get_channel_layer()
    channel = f"test.{uuid.uuid4()}"
    async_to_sync(layer.group_add)(org_group(organization_id), channel)
    return layer, channel


def _punch(node, employee, door):
    return ingest_logs(
        node,
        [
            {
                "id": str(uuid.uuid4()),
                "employee_id": str(employee.id),
                "door_id": str(door.id),
                "timestamp": "2026-10-18T09:00:00Z",
                "direction": "IN",
                "status": "GRANTED",
                "method": "FACIAL",
                "source": "cloud",
            }
        ],
    )


def test_a_granted_punch_is_published_only_to_its_organization(
    acme, globex, acme_node, acme_employee, acme_door
):
    layer, channel = _listen(acme.id)
    foreign_layer, foreign_channel = _listen(globex.id)
    with TestCase.captureOnCommitCallbacks(execute=True):
        result = _punch(acme_node, acme_employee, acme_door)
    assert result["accepted"]
    messages = _drain(layer, channel)
    assert {item["event"] for item in messages} == {"access.granted", "occupancy.changed"}
    granted = next(item for item in messages if item["event"] == "access.granted")
    assert granted["data"]["method"] == "FACIAL"
    assert granted["data"]["source"] == "cloud"
    assert granted["organization_id"] == str(acme.id)
    assert _drain(foreign_layer, foreign_channel) == []


def test_granted_event_carries_the_method_and_denied_does_not_move_occupancy(
    acme, acme_node, acme_employee, acme_door
):
    layer, channel = _listen(acme.id)
    with TestCase.captureOnCommitCallbacks(execute=True):
        ingest_logs(
            acme_node,
            [
                {
                    "id": str(uuid.uuid4()),
                    "employee_id": str(acme_employee.id),
                    "door_id": str(acme_door.id),
                    "timestamp": "2026-10-18T09:30:00Z",
                    "direction": "IN",
                    "status": "DENIED",
                    "denial_reason": "UNKNOWN_CREDENTIAL",
                    "method": "FACIAL",
                    "source": "cloud",
                }
            ],
        )
    messages = _drain(layer, channel)
    assert [item["event"] for item in messages] == ["access.denied"]
    assert messages[0]["data"]["method"] == "FACIAL"
    assert messages[0]["organization_id"] == str(acme.id)


def test_heartbeat_and_enrollment_and_ack_are_published(
    node_client, acme, acme_node, acme_door, acme_reader
):
    layer, channel = _listen(acme.id)
    record_heartbeat(
        acme_node,
        {
            "agent_version": "0.3.0",
            "gateway_connected": True,
            "listening_devices": ["COM3"],
            "queue_size": 2,
            "last_version": 4,
            "commands_connected": True,
        },
    )
    online = _drain(layer, channel)
    assert online[0]["event"] == "node.online"
    assert online[0]["data"]["queue_size"] == 2

    acme_node.last_heartbeat_at = timezone.now() - timedelta(minutes=10)
    acme_node.save(update_fields=["last_heartbeat_at"])
    assert mark_stale_nodes_offline() == 1
    offline = _drain(layer, channel)
    assert offline[0]["event"] == "node.offline"

    created = node_client.post(
        "/api/v1/edge/enrollment-reads/",
        {"reader_id": str(acme_reader.id), "raw": "AA", "payload": "AA", "credential_type": "RFID"},
        format="json",
    )
    assert created.status_code == 201
    reads = _drain(layer, channel)
    assert reads[0]["event"] == "enrollment.read"
    assert reads[0]["data"]["door_id"] == str(acme_door.id)

    command = dispatch_command(
        acme_node,
        "open_door",
        {"door_id": str(acme_door.id), "reason": "visita", "actor": "ada"},
    )
    with TestCase.captureOnCommitCallbacks(execute=True):
        acknowledge(acme_node, command.id, {"status": "GRANTED", "door_opened": True})
    acked = _drain(layer, channel)
    assert acked[0]["event"] == "command.acked"
    assert acked[0]["data"]["id"] == str(command.id)
    assert acked[0]["data"]["status"] == "ACKED"


def test_publish_can_target_a_door_without_reaching_another(acme, acme_node, acme_door):
    other = Door.all_objects.create(
        organization=acme,
        node=acme_node,
        name="Secundaria",
        relay_device_id="RELAY2",
        direction="OUT",
    )
    layer = get_channel_layer()
    door_channel = f"test.{uuid.uuid4()}"
    other_channel = f"test.{uuid.uuid4()}"
    async_to_sync(layer.group_add)(door_group(acme.id, acme_door.id), door_channel)
    async_to_sync(layer.group_add)(door_group(acme.id, other.id), other_channel)
    publish_event(
        acme.id,
        "face.result",
        {"status": "GRANTED"},
        door_id=acme_door.id,
    )
    assert _drain(layer, door_channel)[0]["event"] == "face.result"
    assert _drain(layer, other_channel) == []


@pytest.mark.django_db(transaction=True)
def test_dashboard_and_kiosk_sockets_stay_in_their_groups(
    acme, globex, acme_admin, globex_admin, acme_door
):
    acme_token = issue_tokens(acme_admin, acme)["access"]
    globex_token = issue_tokens(globex_admin, globex)["access"]
    plain, digest = generate_secret()
    Kiosk.all_objects.create(
        organization=acme,
        door=acme_door,
        name="Mostrador",
        kiosk_token_hash=digest,
    )
    other = Door.all_objects.create(
        organization=acme,
        node=acme_door.node,
        name="Bodega",
        relay_device_id="RELAY9",
        direction="OUT",
    )
    _plain_other, other_digest = generate_secret()
    Kiosk.all_objects.create(
        organization=acme,
        door=other,
        name="Bodega",
        kiosk_token_hash=other_digest,
    )

    async def scenario():
        from channels.testing import WebsocketCommunicator

        from config.asgi import application

        dashboard = WebsocketCommunicator(application, "/ws/dashboard/")
        await dashboard.connect()
        await dashboard.send_json_to({"op": "auth", "token": "no"})
        assert (await dashboard.receive_json_from(timeout=2))["op"] == "error"
        await dashboard.disconnect()

        dashboard = WebsocketCommunicator(application, "/ws/dashboard/")
        await dashboard.connect()
        await dashboard.send_json_to({"op": "auth", "token": acme_token})
        assert (await dashboard.receive_json_from(timeout=2))["organization_id"] == str(acme.id)
        foreign = WebsocketCommunicator(application, "/ws/dashboard/")
        await foreign.connect()
        await foreign.send_json_to({"op": "auth", "token": globex_token})
        await foreign.receive_json_from(timeout=2)

        kiosk = WebsocketCommunicator(application, "/ws/kiosk/")
        await kiosk.connect()
        await kiosk.send_json_to({"op": "auth", "token": plain})
        identity = await kiosk.receive_json_from(timeout=2)
        assert identity["door_id"] == str(acme_door.id)
        await kiosk.send_json_to({"op": "ping"})
        assert (await kiosk.receive_json_from(timeout=2))["op"] == "pong"

        layer = get_channel_layer()
        acme_group = org_group(acme.id)
        globex_group = org_group(globex.id)
        door = door_group(acme.id, acme_door.id)
        assert acme_group in layer.groups
        assert globex_group in layer.groups
        assert door in layer.groups
        assert door_group(acme.id, other.id) not in layer.groups
        assert set(layer.groups[acme_group]).isdisjoint(layer.groups[door])
        assert set(layer.groups[acme_group]).isdisjoint(layer.groups[globex_group])

        await dashboard.send_json_to({"op": "ping"})
        assert (await dashboard.receive_json_from(timeout=2))["op"] == "pong"
        await dashboard.send_json_to({"op": "nope"})
        assert (await dashboard.receive_json_from(timeout=2))["op"] == "error"

        await layer.group_send(
            acme_group,
            {
                "type": "realtime.event",
                "message": {"event": "access.granted", "organization_id": str(acme.id), "data": {}},
            },
        )
        delivered = await dashboard.receive_json_from(timeout=2)
        assert delivered["event"] == "access.granted"

        await layer.group_send(
            globex_group,
            {
                "type": "realtime.event",
                "message": {"event": "node.offline", "organization_id": str(globex.id), "data": {}},
            },
        )
        assert (await foreign.receive_json_from(timeout=2))["event"] == "node.offline"

        await layer.group_send(
            door,
            {
                "type": "realtime.event",
                "message": {"event": "face.result", "organization_id": str(acme.id), "data": {}},
            },
        )
        assert (await kiosk.receive_json_from(timeout=2))["event"] == "face.result"

        await dashboard.disconnect()
        await foreign.disconnect()
        await kiosk.disconnect()
        assert acme_group not in layer.groups
        assert door not in layer.groups

    try:
        asyncio.run(scenario())
    finally:
        connections.close_all()
