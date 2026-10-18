import asyncio
import threading
import time
import uuid
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.db import connections
from django.test import override_settings
from django.utils import timezone
from rest_framework.settings import api_settings
from rest_framework.test import APIClient

from apps.access.models import AccessNode
from apps.sync.models import EdgeCommand
from apps.sync.signals import device_status_changed
from apps.sync.tasks import expire_edge_commands, mark_stale_nodes_offline_task


def _dispatch(client, node, command_type, payload, wait=0):
    return client.post(
        f"/api/v1/nodes/{node.id}/commands/",
        {"type": command_type, "payload": payload, "wait": wait},
        format="json",
    )


def test_heartbeat_marks_the_node_online_and_stale_task_marks_it_offline(node_client, acme_node):
    events = []

    def handler(sender, node, is_online, **kwargs):
        events.append((node.pk, is_online))

    device_status_changed.connect(handler)
    try:
        response = node_client.post(
            "/api/v1/edge/heartbeat/",
            {
                "agent_version": "0.1.0",
                "gateway_connected": True,
                "listening_devices": ["COM3"],
                "queue_size": 4,
                "last_version": 12,
                "commands_connected": True,
                "gateway_version": "gw-2",
            },
            format="json",
        )
        assert response.status_code == 200
        acme_node.refresh_from_db()
        assert acme_node.is_online is True
        assert acme_node.queue_size == 4
        assert acme_node.last_sync_version == 12
        assert acme_node.gateway_version_reported == "gw-2"
        assert events == [(acme_node.pk, True)]

        again = node_client.post(
            "/api/v1/edge/heartbeat/",
            {
                "gateway_connected": True,
                "queue_size": 0,
                "last_version": 12,
                "commands_connected": False,
            },
            format="json",
        )
        assert again.status_code == 200
        assert events == [(acme_node.pk, True)]

        AccessNode.all_objects.filter(pk=acme_node.pk).update(
            last_heartbeat_at=timezone.now() - timedelta(minutes=10)
        )
        assert mark_stale_nodes_offline_task() == 1
        acme_node.refresh_from_db()
        assert acme_node.is_online is False
        assert events[-1] == (acme_node.pk, False)
        assert mark_stale_nodes_offline_task() == 0
    finally:
        device_status_changed.disconnect(handler)


def test_dispatch_poll_and_idempotent_ack(
    operator_client, viewer_client, node_client, acme_node, acme_door, globex_node
):
    denied = viewer_client.post(
        f"/api/v1/nodes/{acme_node.id}/commands/",
        {"type": "sync_now", "payload": {}},
        format="json",
    )
    assert denied.status_code == 403
    foreign = _dispatch(operator_client, globex_node, "sync_now", {})
    assert foreign.status_code == 404
    missing_door = _dispatch(
        operator_client,
        acme_node,
        "open_door",
        {"door_id": str(uuid.uuid4()), "reason": "visita", "actor": "ada"},
    )
    assert missing_door.status_code == 400

    created = _dispatch(
        operator_client,
        acme_node,
        "open_door",
        {"door_id": str(acme_door.id), "reason": "visita"},
    )
    assert created.status_code == 200
    assert created.data["status"] == "PENDING"
    assert created.data["payload"]["actor"] == "acme.operator"
    polled = node_client.get("/api/v1/edge/commands/?wait=0")
    assert polled.status_code == 200
    assert polled.data["commands"][0]["id"] == created.data["id"]
    assert polled.data["commands"][0]["status"] == "SENT"
    ack = node_client.post(
        f"/api/v1/edge/commands/{created.data['id']}/ack/",
        {"result": {"status": "GRANTED", "door_opened": True}},
        format="json",
    )
    assert ack.status_code == 200
    assert ack.data["status"] == "ACKED"
    repeated = node_client.post(
        f"/api/v1/edge/commands/{created.data['id']}/ack/",
        {"result": {"status": "FAILED"}},
        format="json",
    )
    assert repeated.status_code == 200
    assert repeated.data["status"] == "ACKED"
    assert repeated.data["result"]["door_opened"] is True
    empty = node_client.get("/api/v1/edge/commands/?wait=0")
    assert empty.data["commands"] == []
    listed = operator_client.get(f"/api/v1/nodes/{acme_node.id}/commands/")
    assert listed.data[0]["id"] == created.data["id"]


def test_expired_command_is_not_retried(node_client, operator_client, acme_node):
    created = _dispatch(operator_client, acme_node, "reload", {})
    EdgeCommand.all_objects.filter(pk=created.data["id"]).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    polled = node_client.get("/api/v1/edge/commands/?wait=0")
    assert polled.data["commands"] == []
    command = EdgeCommand.all_objects.get(pk=created.data["id"])
    assert command.status == EdgeCommand.Status.EXPIRED
    assert expire_edge_commands() == 0
    ack = node_client.post(
        f"/api/v1/edge/commands/{command.id}/ack/",
        {"result": {"status": "GRANTED"}},
        format="json",
    )
    assert ack.status_code == 409
    command.refresh_from_db()
    assert command.status == EdgeCommand.Status.EXPIRED


def test_failed_ack_and_command_validation(
    node_client, operator_client, acme_node, acme_door, acme_reader
):
    created = _dispatch(operator_client, acme_node, "sync_now", {})
    ack = node_client.post(
        f"/api/v1/edge/commands/{created.data['id']}/ack/",
        {"result": {"status": "FAILED"}},
        format="json",
    )
    assert ack.data["status"] == "FAILED"
    bad = _dispatch(
        operator_client,
        acme_node,
        "identification",
        {
            "door_id": str(acme_door.id),
            "type": "RFID",
            "payload": "",
            "request_id": str(uuid.uuid4()),
        },
    )
    assert bad.status_code == 400
    enrolled = _dispatch(
        operator_client,
        acme_node,
        "enrollment_mode",
        {"reader_id": str(acme_reader.id), "seconds": 30},
    )
    assert enrolled.status_code == 200
    assert node_client.get("/api/v1/edge/commands/?wait=no").status_code == 400
    assert (
        node_client.post(
            f"/api/v1/edge/commands/{uuid.uuid4()}/ack/",
            {"result": {}},
            format="json",
        ).status_code
        == 404
    )


def test_node_throttle(node_client, settings):
    cache.clear()
    with override_settings(
        REST_FRAMEWORK={
            **settings.REST_FRAMEWORK,
            "DEFAULT_THROTTLE_RATES": {"edge_node": "1/min"},
        }
    ):
        api_settings.reload()
        first = node_client.get("/api/v1/edge/sync/delta/")
        second = node_client.get("/api/v1/edge/sync/delta/")
    api_settings.reload()
    cache.clear()
    assert first.status_code == 200
    assert second.status_code == 429


@pytest.mark.django_db(transaction=True)
def test_open_door_reaches_a_waiting_node_quickly(acme_node, acme_door, operator_client):
    errors = []

    def worker():
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {acme_node.plaintext_api_key}")
        try:
            response = client.get("/api/v1/edge/commands/?wait=5")
            command = response.data["commands"][0]
            ack = client.post(
                f"/api/v1/edge/commands/{command['id']}/ack/",
                {"result": {"status": "GRANTED", "door_opened": True}},
                format="json",
            )
            if ack.status_code != 200:
                errors.append(ack.data)
        except Exception as exc:
            errors.append(exc)
        finally:
            connections.close_all()

    thread = threading.Thread(target=worker)
    thread.start()
    time.sleep(0.4)
    started = time.monotonic()
    response = _dispatch(
        operator_client,
        acme_node,
        "open_door",
        {"door_id": str(acme_door.id), "reason": "visita", "actor": "ada"},
        wait=3,
    )
    thread.join(timeout=5)
    assert not errors
    assert response.status_code == 200
    assert response.data["status"] == "ACKED"
    assert time.monotonic() - started < 0.5


@pytest.mark.django_db(transaction=True)
def test_websocket_delivers_pending_commands_and_ack(acme_node, acme_door):
    from apps.sync.commands import dispatch_command

    command = dispatch_command(
        acme_node,
        "open_door",
        {"door_id": str(acme_door.id), "reason": "visita", "actor": "ada"},
    )

    async def scenario():
        from channels.testing import WebsocketCommunicator

        from config.asgi import application

        communicator = WebsocketCommunicator(application, "/ws/edge/")
        connected, _ = await communicator.connect()
        assert connected
        await communicator.send_json_to({"op": "ping"})
        rejected = await communicator.receive_json_from(timeout=2)
        assert rejected["op"] == "error"
        await communicator.disconnect()

        communicator = WebsocketCommunicator(application, "/ws/edge/")
        await communicator.connect()
        await communicator.send_json_to({"op": "auth", "token": "incorrecta"})
        invalid = await communicator.receive_json_from(timeout=2)
        assert invalid["op"] == "error"
        await communicator.disconnect()

        communicator = WebsocketCommunicator(application, "/ws/edge/")
        await communicator.connect()
        await communicator.send_json_to({"op": "auth", "token": acme_node.plaintext_api_key})
        authenticated = await communicator.receive_json_from(timeout=2)
        assert authenticated["op"] == "auth_ok"
        delivered = await communicator.receive_json_from(timeout=2)
        assert delivered["op"] == "command"
        assert delivered["id"] == str(command.id)
        await communicator.send_json_to({"op": "ping"})
        assert (await communicator.receive_json_from(timeout=2))["op"] == "pong"
        await communicator.send_json_to({"op": "nope"})
        assert (await communicator.receive_json_from(timeout=2))["op"] == "error"
        await communicator.send_json_to(
            {
                "op": "ack",
                "id": str(command.id),
                "result": {"status": "GRANTED", "door_opened": True},
            }
        )
        acknowledged = await communicator.receive_json_from(timeout=2)
        assert acknowledged["status"] == "ACKED"
        await communicator.disconnect()

    asyncio.run(scenario())
    connections.close_all()
    command.refresh_from_db()
    acme_node.refresh_from_db()
    assert command.status == EdgeCommand.Status.ACKED
    assert acme_node.commands_connected is False
