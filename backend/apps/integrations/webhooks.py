"""Despacho y entrega de webhooks firmados por organización."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.request
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.access.models import AccessStatus
from apps.integrations.models import (
    WEBHOOK_EVENTS,
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookSubscription,
)
from apps.sync.formatting import isoformat

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 8
RESPONSE_BODY_LIMIT = 2000
TIMEOUT_SECONDS = 10.0
# 1 min → 24 h, ocho intentos.
RETRY_DELAYS = (60, 120, 300, 900, 1800, 3600, 14400, 86400)


def sign_body(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(secret: str, body: bytes, header: str) -> bool:
    expected = sign_body(secret, body)
    return hmac.compare_digest(expected, header or "")


def access_payload(log) -> dict:
    return {
        "id": str(log.id),
        "organization_id": str(log.organization_id),
        "node_id": str(log.node_id),
        "door_id": str(log.door_id) if log.door_id else None,
        "employee_id": str(log.employee_id) if log.employee_id else None,
        "timestamp": isoformat(log.timestamp),
        "direction": log.direction,
        "status": log.status,
        "denial_reason": log.denial_reason,
        "method": log.method,
        "source": log.source,
    }


def device_payload(node, is_online: bool) -> dict:
    return {
        "organization_id": str(node.organization_id),
        "node_id": str(node.id),
        "name": node.name,
        "site": node.site,
        "is_online": bool(is_online),
        "agent_version": node.agent_version,
        "queue_size": node.queue_size,
        "commands_connected": node.commands_connected,
        "gateway_connected": node.gateway_connected,
        "last_heartbeat_at": isoformat(node.last_heartbeat_at),
    }


def enqueue_event(organization_id, event: str, data: dict) -> int:
    if event not in WEBHOOK_EVENTS:
        return 0
    subscriptions = list(
        WebhookSubscription.all_objects.filter(
            organization_id=organization_id,
            is_active=True,
        )
    )
    created = 0
    for subscription in subscriptions:
        if event not in (subscription.events or []):
            continue
        delivery = WebhookDelivery.all_objects.create(
            organization_id=organization_id,
            subscription=subscription,
            event=event,
            payload=data,
            status=WebhookDeliveryStatus.PENDING,
            next_retry_at=timezone.now(),
        )
        transaction.on_commit(lambda delivery_id=str(delivery.id): _schedule(delivery_id, 0))
        created += 1
    return created


def enqueue_access_log(log) -> int:
    event = "access.granted" if log.status == AccessStatus.GRANTED else "access.denied"
    return enqueue_event(log.organization_id, event, access_payload(log))


def enqueue_device_status(node, is_online: bool) -> int:
    return enqueue_event(
        node.organization_id,
        "device.status_changed",
        device_payload(node, is_online),
    )


def sample_payload(organization_id, event: str) -> dict:
    now = isoformat(timezone.now())
    if event == "device.status_changed":
        return {
            "organization_id": str(organization_id),
            "node_id": "00000000-0000-4000-8000-000000000001",
            "name": "Nodo de prueba",
            "site": "Demo",
            "is_online": True,
            "agent_version": "test",
            "queue_size": 0,
            "commands_connected": True,
            "gateway_connected": True,
            "last_heartbeat_at": now,
        }
    return {
        "id": "00000000-0000-4000-8000-000000000099",
        "organization_id": str(organization_id),
        "node_id": "00000000-0000-4000-8000-000000000001",
        "door_id": None,
        "employee_id": None,
        "timestamp": now,
        "direction": "IN",
        "status": "GRANTED" if event == "access.granted" else "DENIED",
        "denial_reason": "" if event == "access.granted" else "UNKNOWN_CREDENTIAL",
        "method": "RFID",
        "source": "gateway",
        "test": True,
    }


def deliver_once(delivery_id: str) -> str:
    delivery = (
        WebhookDelivery.all_objects.select_related("subscription")
        .filter(pk=delivery_id)
        .first()
    )
    if delivery is None:
        return "missing"
    if delivery.status in {WebhookDeliveryStatus.SUCCESS, WebhookDeliveryStatus.EXHAUSTED}:
        return delivery.status

    subscription = delivery.subscription
    if not subscription.is_active:
        delivery.status = WebhookDeliveryStatus.EXHAUSTED
        delivery.response_body = "Suscripción inactiva."
        delivery.completed_at = timezone.now()
        delivery.save(update_fields=["status", "response_body", "completed_at"])
        return delivery.status

    body = json.dumps(delivery.payload, ensure_ascii=False, separators=(",", ":")).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "attendance-system-webhooks/1.0",
        "X-Event": delivery.event,
        "X-Delivery-Id": str(delivery.id),
        "X-Organization-Id": str(delivery.organization_id),
        "X-Signature": sign_body(subscription.secret, body),
    }
    delivery.attempt += 1
    try:
        request = urllib.request.Request(
            subscription.url,
            data=body,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read().decode(errors="replace")
            delivery.response_status = response.status
            delivery.response_body = raw[:RESPONSE_BODY_LIMIT]
            ok = 200 <= response.status < 300
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        delivery.response_status = exc.code
        delivery.response_body = raw[:RESPONSE_BODY_LIMIT]
        ok = False
    except urllib.error.URLError as exc:
        delivery.response_status = None
        delivery.response_body = str(exc.reason)[:RESPONSE_BODY_LIMIT]
        ok = False

    if ok:
        delivery.status = WebhookDeliveryStatus.SUCCESS
        delivery.next_retry_at = None
        delivery.completed_at = timezone.now()
        delivery.save(
            update_fields=[
                "attempt",
                "status",
                "response_status",
                "response_body",
                "next_retry_at",
                "completed_at",
            ]
        )
        return delivery.status

    if delivery.attempt >= MAX_ATTEMPTS:
        delivery.status = WebhookDeliveryStatus.EXHAUSTED
        delivery.next_retry_at = None
        delivery.completed_at = timezone.now()
        delivery.save(
            update_fields=[
                "attempt",
                "status",
                "response_status",
                "response_body",
                "next_retry_at",
                "completed_at",
            ]
        )
        return delivery.status

    delay = RETRY_DELAYS[min(delivery.attempt - 1, len(RETRY_DELAYS) - 1)]
    delivery.status = WebhookDeliveryStatus.FAILED
    delivery.next_retry_at = timezone.now() + timedelta(seconds=delay)
    delivery.save(
        update_fields=[
            "attempt",
            "status",
            "response_status",
            "response_body",
            "next_retry_at",
        ]
    )
    _schedule(str(delivery.id), delay)
    return delivery.status


def resend_delivery(delivery: WebhookDelivery) -> WebhookDelivery:
    clone = WebhookDelivery.all_objects.create(
        organization_id=delivery.organization_id,
        subscription=delivery.subscription,
        event=delivery.event,
        payload=delivery.payload,
        status=WebhookDeliveryStatus.PENDING,
        next_retry_at=timezone.now(),
    )
    transaction.on_commit(lambda: _schedule(str(clone.id), 0))
    return clone


def _schedule(delivery_id: str, countdown: int) -> None:
    from apps.integrations.tasks import deliver_webhook

    deliver_webhook.apply_async(args=[delivery_id], countdown=countdown)
