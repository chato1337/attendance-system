import time
import uuid

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.access.models import (
    AccessLog,
    AccessMethod,
    AccessSource,
    AccessStatus,
    DenialReason,
)
from apps.integrations.faceauth.client import FaceAuthClient, FaceAuthError
from apps.integrations.faceauth.flow import (
    FaceFlowError,
    TokenAlreadyUsed,
    parse_user_id,
    require_integration,
    token_fingerprint,
)
from apps.kiosk.models import FaceIdentificationRequest, Kiosk
from apps.people.models import Credential
from apps.sync.commands import CommandValidationError, dispatch_command
from apps.sync.models import EdgeCommand
from apps.sync.realtime import publish_event
from apps.sync.signals import access_log_created

DENIAL_TEXT = {
    DenialReason.UNKNOWN_CREDENTIAL: "Credencial desconocida.",
    DenialReason.INACTIVE: "La credencial no está activa.",
    DenialReason.EXPIRED: "La credencial está vencida.",
    DenialReason.APB_VIOLATION: "El anti-passback impidió el acceso.",
    DenialReason.FACE_NOT_ALLOWED: "Esta puerta no admite rostro.",
    DenialReason.NODE_OFFLINE: "La puerta no responde. Use su tarjeta.",
}


def identify_face(kiosk: Kiosk, redirect_token: str) -> FaceIdentificationRequest:
    token = (redirect_token or "").strip()
    if not token or len(token) > 8192:
        raise FaceFlowError("invalid_token", "Token inválido.", 400)
    integration = require_integration(kiosk.organization_id)
    digest, jti = token_fingerprint(token)
    if FaceIdentificationRequest.all_objects.filter(token_digest=digest).exists():
        raise TokenAlreadyUsed()

    try:
        with transaction.atomic():
            request = FaceIdentificationRequest.all_objects.create(
                organization=kiosk.organization,
                kiosk=kiosk,
                door=kiosk.door,
                token_digest=digest,
                token_jti=jti,
            )
    except IntegrityError as exc:
        raise TokenAlreadyUsed() from exc

    started = time.monotonic()
    client = FaceAuthClient(integration)
    try:
        identity = client.verify_token(token)
    except FaceAuthError as exc:
        return _finish(
            request,
            FaceIdentificationRequest.Status.REJECTED,
            exc.code,
            exc.message,
            verify_ms=_elapsed(started),
        )

    verify_ms = _elapsed(started)
    if identity.get("app_id") and identity["app_id"] != integration.app_id:
        return _finish(
            request,
            FaceIdentificationRequest.Status.REJECTED,
            "invalid_token",
            "El token pertenece a otra aplicación.",
            verify_ms=verify_ms,
        )

    user_id = parse_user_id(identity["user_id"])
    request.faceauth_user_id = user_id
    request.email = str(identity.get("email") or "")[:254]
    request.timings = {"verify_ms": verify_ms}

    if not kiosk.door.face_enabled:
        return _deny(
            request,
            DenialReason.FACE_NOT_ALLOWED,
            FaceIdentificationRequest.Status.DENIED,
        )

    credential = (
        Credential.all_objects.select_related("employee")
        .filter(
            organization_id=kiosk.organization_id,
            type=Credential.CredentialType.FACIAL,
            payload=str(user_id),
            is_active=True,
            deleted_at__isnull=True,
        )
        .first()
    )
    if credential is None:
        return _deny(
            request,
            DenialReason.UNKNOWN_CREDENTIAL,
            FaceIdentificationRequest.Status.UNKNOWN_FACE,
        )
    if not credential.employee.is_active or credential.employee.deleted_at:
        return _deny(
            request,
            DenialReason.INACTIVE,
            FaceIdentificationRequest.Status.DENIED,
            employee=credential.employee,
            credential=credential,
        )

    try:
        command = dispatch_command(
            kiosk.door.node,
            EdgeCommand.Type.IDENTIFICATION,
            {
                "door_id": str(kiosk.door_id),
                "type": Credential.CredentialType.FACIAL,
                "payload": str(user_id),
                "request_id": str(request.id),
            },
            timeout=settings.FACE_IDENTIFY_TIMEOUT_SECONDS,
        )
    except CommandValidationError:
        return _deny(
            request,
            DenialReason.NODE_OFFLINE,
            FaceIdentificationRequest.Status.NODE_UNREACHABLE,
            employee=credential.employee,
            credential=credential,
        )

    request.command = command
    request.timings = {**request.timings, "dispatch_ms": _elapsed(started) - verify_ms}
    if command.status != EdgeCommand.Status.ACKED:
        return _deny(
            request,
            DenialReason.NODE_OFFLINE,
            FaceIdentificationRequest.Status.NODE_UNREACHABLE,
            employee=credential.employee,
            credential=credential,
        )

    result = command.result or {}
    granted = str(result.get("status", "")).upper() == "GRANTED"
    reason = str(result.get("denial_reason") or "")
    edge_log_id = _optional_uuid(result.get("log_id"))
    message = "Acceso concedido." if granted else DENIAL_TEXT.get(reason, "Acceso denegado.")
    return _finish(
        request,
        FaceIdentificationRequest.Status.GRANTED
        if granted
        else FaceIdentificationRequest.Status.DENIED,
        "" if granted else reason,
        message,
        edge_log_id=edge_log_id,
    )


def identification_body(request: FaceIdentificationRequest) -> dict:
    log_id = request.access_log_id or request.edge_log_id
    return {
        "id": str(request.id),
        "status": request.status,
        "code": request.code,
        "message": request.message,
        "door_id": str(request.door_id),
        "kiosk_id": str(request.kiosk_id),
        "log_id": str(log_id) if log_id else None,
        "created_at": request.created_at,
        "completed_at": request.completed_at,
    }


def _deny(request, reason, status, employee=None, credential=None):
    log = _cloud_denial(request.kiosk, reason, employee=employee, credential=credential)
    text = DENIAL_TEXT.get(reason, "Acceso denegado.")
    return _finish(request, status, reason, text, access_log=log)


def _cloud_denial(kiosk, reason, employee=None, credential=None) -> AccessLog:
    log = AccessLog.all_objects.create(
        organization=kiosk.organization,
        node=kiosk.door.node,
        door=kiosk.door,
        employee=employee,
        credential=credential,
        timestamp=timezone.now(),
        direction=kiosk.door.direction,
        status=AccessStatus.DENIED,
        denial_reason=reason,
        method=AccessMethod.FACIAL,
        source=AccessSource.CLOUD,
    )
    transaction.on_commit(lambda: access_log_created.send(sender=AccessLog, log=log))
    return log


def _finish(
    request,
    status,
    code,
    message,
    *,
    access_log=None,
    edge_log_id=None,
    verify_ms=None,
):
    request.status = status
    request.code = (code or "")[:64]
    request.message = (message or "")[:500]
    if access_log is not None:
        request.access_log = access_log
    if edge_log_id is not None:
        request.edge_log_id = edge_log_id
    if verify_ms is not None:
        request.timings = {**(request.timings or {}), "verify_ms": verify_ms}
    request.completed_at = timezone.now()
    request.save()
    publish_face_result(request)
    return request


def publish_face_result(request: FaceIdentificationRequest) -> None:
    publish_event(
        request.organization_id,
        "face.result",
        {
            "request_id": str(request.id),
            "status": request.status,
            "code": request.code,
            "message": request.message,
            "door_id": str(request.door_id),
            "kiosk_id": str(request.kiosk_id),
            "log_id": str(request.access_log_id or request.edge_log_id or "") or None,
        },
        node_id=request.door.node_id,
        door_id=request.door_id,
    )


def _elapsed(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _optional_uuid(value):
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None
