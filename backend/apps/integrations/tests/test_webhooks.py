import hashlib
import hmac
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import pytest
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.access.models import AccessLog, AccessStatus, Direction
from apps.integrations.models import (
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookSubscription,
)
from apps.integrations.webhooks import deliver_once, enqueue_event, sign_body, verify_signature
from apps.people.models import Employee
from apps.sync.signals import access_log_created, device_status_changed


class _Recorder(BaseHTTPRequestHandler):
    hits: list[dict] = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        _Recorder.hits.append(
            {
                "body": body,
                "headers": {key: value for key, value in self.headers.items()},
            }
        )
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, format, *args):
        return


@pytest.fixture
def receiver():
    _Recorder.hits = []
    server = HTTPServer(("127.0.0.1", 0), _Recorder)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    yield f"http://127.0.0.1:{port}/hook"
    server.shutdown()


def test_signature_roundtrip():
    body = b'{"hello":"world"}'
    header = sign_body("super-secret", body)
    assert header.startswith("sha256=")
    assert verify_signature("super-secret", body, header)
    assert not verify_signature("other", body, header)


def test_access_log_enqueues_and_delivers(acme, acme_node, receiver):
    secret = "hook-secret-acme"
    WebhookSubscription.all_objects.create(
        organization=acme,
        name="ERP",
        url=receiver,
        secret=secret,
        events=["access.granted", "access.denied"],
    )
    employee = Employee.all_objects.create(
        organization=acme,
        document_id="W-1",
        first_name="Ana",
        last_name="Webhook",
    )
    log = AccessLog.all_objects.create(
        organization=acme,
        node=acme_node,
        employee=employee,
        timestamp=timezone.now(),
        direction=Direction.IN,
        status=AccessStatus.GRANTED,
        method="RFID",
        source="gateway",
    )
    with TestCase.captureOnCommitCallbacks(execute=True):
        access_log_created.send(sender=AccessLog, log=log)
    delivery = WebhookDelivery.all_objects.get(organization=acme)
    assert delivery.status == WebhookDeliveryStatus.SUCCESS
    assert delivery.attempt == 1
    assert len(_Recorder.hits) == 1
    hit = _Recorder.hits[0]
    assert hit["headers"]["X-Event"] == "access.granted"
    assert hit["headers"]["X-Delivery-Id"] == str(delivery.id)
    assert hit["headers"]["X-Organization-Id"] == str(acme.id)
    assert verify_signature(secret, hit["body"], hit["headers"]["X-Signature"])
    payload = json.loads(hit["body"])
    assert payload["organization_id"] == str(acme.id)
    assert payload["method"] == "RFID"
    assert payload["source"] == "gateway"


def test_failed_delivery_retries_then_exhausts(acme):
    WebhookSubscription.all_objects.create(
        organization=acme,
        name="Caído",
        url="http://127.0.0.1:1/nope",
        secret="secret",
        events=["access.granted"],
    )
    with TestCase.captureOnCommitCallbacks(execute=True):
        enqueue_event(
            acme.id,
            "access.granted",
            {"organization_id": str(acme.id), "test": True},
        )
    delivery = WebhookDelivery.all_objects.get(organization=acme)
    # Con Celery eager los reintentos se encadenan hasta agotar.
    assert delivery.status == WebhookDeliveryStatus.EXHAUSTED
    assert delivery.attempt == 8

    # Un intento aislado también agota al llegar al máximo.
    clone = WebhookDelivery.all_objects.create(
        organization=acme,
        subscription=delivery.subscription,
        event="access.granted",
        payload={"organization_id": str(acme.id)},
        status=WebhookDeliveryStatus.PENDING,
        attempt=7,
    )
    status = deliver_once(str(clone.id))
    clone.refresh_from_db()
    assert status == WebhookDeliveryStatus.EXHAUSTED
    assert clone.attempt == 8


def test_device_status_and_panel_crud(
    acme, globex, acme_client, globex_client, acme_node, receiver
):
    created = acme_client.post(
        "/api/v1/webhooks/",
        {
            "name": "Nómina",
            "url": receiver,
            "events": ["access.granted", "device.status_changed"],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    secret = created.data["secret_value"]
    assert secret
    listed = acme_client.get(f"/api/v1/webhooks/{created.data['id']}/")
    assert "secret" not in listed.data
    assert "secret_value" not in listed.data

    assert globex_client.get(f"/api/v1/webhooks/{created.data['id']}/").status_code == 404
    assert globex_client.get("/api/v1/webhooks/").data["count"] == 0

    with TestCase.captureOnCommitCallbacks(execute=True):
        test = acme_client.post(
            f"/api/v1/webhooks/{created.data['id']}/test/",
            {"event": "access.granted"},
            format="json",
        )
    assert test.status_code == 202
    assert WebhookDelivery.all_objects.filter(organization=acme, event="access.granted").exists()

    with TestCase.captureOnCommitCallbacks(execute=True):
        device_status_changed.send(sender=None, node=acme_node, is_online=True)
    assert WebhookDelivery.all_objects.filter(
        organization=acme, event="device.status_changed"
    ).exists()

    deliveries = acme_client.get(f"/api/v1/webhooks/{created.data['id']}/deliveries/")
    assert deliveries.status_code == 200
    first_id = deliveries.data["results"][0]["id"]
    with TestCase.captureOnCommitCallbacks(execute=True):
        resent = acme_client.post(f"/api/v1/webhook-deliveries/{first_id}/resend/")
    assert resent.status_code == 202


def test_api_token_scopes_and_bulk(acme, acme_client, globex_client):
    created = acme_client.post(
        "/api/v1/api-tokens/",
        {"name": "ERP", "scopes": ["employees:read", "employees:write"]},
        format="json",
    )
    assert created.status_code == 201, created.data
    token = created.data["token"]
    assert token.startswith("atk_")
    assert "token" not in acme_client.get(f"/api/v1/api-tokens/{created.data['id']}/").data

    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert api.get("/api/v1/employees/").status_code == 200

    bulk = api.post(
        "/api/v1/employees/bulk/",
        {
            "employees": [
                {
                    "document_id": "B-1",
                    "first_name": "Luis",
                    "last_name": "Bulk",
                    "department": "Nómina",
                    "email": "luis@acme.test",
                },
                {
                    "document_id": "B-1",
                    "first_name": "Luis",
                    "last_name": "Actualizado",
                    "department": "Nómina",
                },
            ]
        },
        format="json",
    )
    assert bulk.status_code in {200, 207}, bulk.data
    assert bulk.data["created"] == 1
    assert bulk.data["updated"] == 1
    assert Employee.all_objects.filter(organization=acme, document_id="B-1").count() == 1

    foreign_token = globex_client.post(
        "/api/v1/api-tokens/",
        {"name": "ERP", "scopes": ["employees:read"]},
        format="json",
    ).data["token"]
    other = APIClient()
    other.credentials(HTTP_AUTHORIZATION=f"Bearer {foreign_token}")
    assert other.get("/api/v1/employees/").data["count"] == 0

    read_only = acme_client.post(
        "/api/v1/api-tokens/",
        {"name": "Solo lectura", "scopes": ["employees:read"]},
        format="json",
    ).data["token"]
    reader = APIClient()
    reader.credentials(HTTP_AUTHORIZATION=f"Bearer {read_only}")
    denied = reader.post(
        "/api/v1/employees/bulk/",
        {"employees": [{"document_id": "X", "first_name": "A", "last_name": "B"}]},
        format="json",
    )
    assert denied.status_code == 403


def test_signature_matches_python_example():
    secret = "demo-secret"
    body = b'{"organization_id":"acme","status":"GRANTED"}'
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert sign_body(secret, body) == expected
