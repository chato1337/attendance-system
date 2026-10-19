import uuid
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.access.models import AccessLog, DenialReason
from apps.accounts.models import User
from apps.common.secrets import generate_secret
from apps.integrations.faceauth.client import FaceAuthClient, FaceAuthError, http_request
from apps.integrations.models import FaceAuthIntegration, FaceAuthPendingDeletion
from apps.kiosk.models import FaceEnrollmentSession, FaceIdentificationRequest, Kiosk
from apps.people.models import Credential, Employee
from apps.sync.commands import dispatch_command
from apps.sync.models import EdgeCommand
from apps.tenants.models import Membership

FACE_USER = uuid.UUID("11111111-1111-4111-8111-111111111111")
SECRET = "super-secret-face-key"


def _integration(organization, **extra):
    values = {
        "app_id": "app_acme",
        "api_key": SECRET,
        "api_url": "http://faceauth.test/api/v1",
        "web_url": "http://faceauth.test",
        "enabled": True,
    }
    values.update(extra)
    return FaceAuthIntegration.all_objects.create(organization=organization, **values)


def _kiosk_client(organization, door, name="Mostrador"):
    plain, digest = generate_secret()
    kiosk = Kiosk.all_objects.create(
        organization=organization,
        door=door,
        name=name,
        kiosk_token_hash=digest,
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {plain}")
    return kiosk, client, plain


def _face_employee(organization, document_id="1", email="ana@acme.test"):
    return Employee.all_objects.create(
        organization=organization,
        document_id=document_id,
        first_name="Ana",
        last_name="Ruiz",
        email=email,
    )


def _credential(employee, user_id=FACE_USER):
    return Credential.all_objects.create(
        organization=employee.organization,
        employee=employee,
        type=Credential.CredentialType.FACIAL,
        payload=str(user_id),
        source=Credential.Source.FACEAUTH,
    )


def _identity(email="ana@acme.test", user_id=FACE_USER, app_id="app_acme"):
    return {
        "valid": True,
        "user_id": str(user_id),
        "app_id": app_id,
        "email": email,
        "first_name": "Ana",
        "last_name": "Ruiz",
    }


def _ack_granted(node, command_type, payload, timeout=None):
    command = dispatch_command(node, command_type, payload, timeout=0)
    command.status = EdgeCommand.Status.ACKED
    command.result = {
        "status": "GRANTED",
        "denial_reason": "",
        "log_id": str(uuid.uuid4()),
        "door_opened": True,
    }
    command.acked_at = timezone.now()
    command.save(update_fields=["status", "result", "acked_at"])
    return command


@pytest.fixture
def face_door(acme_door):
    acme_door.face_enabled = True
    acme_door.save(update_fields=["face_enabled", "updated_at"])
    return acme_door


def test_verify_does_not_retry_and_maps_errors(monkeypatch):
    calls = {"n": 0}

    def once(method, url, data, headers, timeout):
        calls["n"] += 1
        assert headers["X-Api-Key"] == SECRET
        assert "token" in data.decode()
        return 401, {"code": "token_already_used", "message": "consumido"}

    monkeypatch.setattr("apps.integrations.faceauth.client.http_request", once)
    integration = FaceAuthIntegration(
        app_id="app_acme",
        api_key=SECRET,
        api_url="http://faceauth.test/api/v1",
    )
    with pytest.raises(FaceAuthError) as caught:
        FaceAuthClient(integration).verify_token("jwt")
    assert calls["n"] == 1
    assert caught.value.code == "token_already_used"
    assert http_request.__name__ == "http_request"


def test_api_key_is_write_only(acme_client, acme):
    saved = acme_client.patch(
        "/api/v1/faceauth-integration/",
        {"app_id": "app_acme", "api_key": SECRET, "enabled": True},
        format="json",
    )
    assert saved.status_code == 200
    assert SECRET not in str(saved.data)
    assert saved.data["api_key_set"] is True
    assert "api_key" not in saved.data
    again = acme_client.get("/api/v1/faceauth-integration/")
    assert SECRET not in str(again.data)


def test_granted_identification_reuses_the_agent_pipeline(face_door, acme, monkeypatch):
    _integration(acme)
    employee = _face_employee(acme)
    _credential(employee)
    _kiosk, client, _token = _kiosk_client(acme, face_door)
    monkeypatch.setattr(FaceAuthClient, "verify_token", lambda self, token: _identity())
    monkeypatch.setattr("apps.integrations.faceauth.identify.dispatch_command", _ack_granted)

    response = client.post(
        "/api/v1/kiosk/face-identify/",
        {"redirect_token": "header.payload.sig"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["status"] == "GRANTED"
    assert response.data["message"] == "Acceso concedido."
    command = EdgeCommand.all_objects.get()
    assert command.type == EdgeCommand.Type.IDENTIFICATION
    assert command.payload["type"] == "FACIAL"
    assert command.payload["payload"] == str(FACE_USER)
    assert command.payload["door_id"] == str(face_door.id)
    assert AccessLog.all_objects.count() == 0


def test_reused_token_does_not_create_a_second_log(face_door, acme, monkeypatch):
    _integration(acme)
    _kiosk, client, _token = _kiosk_client(acme, face_door)
    calls = {"n": 0}

    def verify(self, token):
        calls["n"] += 1
        return _identity()

    monkeypatch.setattr(FaceAuthClient, "verify_token", verify)
    body = {"redirect_token": "header.payload.sig"}
    first = client.post("/api/v1/kiosk/face-identify/", body, format="json")
    second = client.post("/api/v1/kiosk/face-identify/", body, format="json")

    assert first.status_code == 200
    assert first.data["status"] == "UNKNOWN_FACE"
    assert second.status_code == 409
    assert second.data["code"] == "token_already_used"
    assert calls["n"] == 1
    assert AccessLog.all_objects.count() == 1
    assert FaceIdentificationRequest.all_objects.count() == 1


def test_unknown_face_and_other_app_and_unreachable(face_door, acme, monkeypatch):
    _integration(acme)
    _kiosk, client, _token = _kiosk_client(acme, face_door)
    monkeypatch.setattr(
        FaceAuthClient,
        "verify_token",
        lambda self, token: _identity(app_id="app_other"),
    )
    foreign = client.post(
        "/api/v1/kiosk/face-identify/",
        {"redirect_token": "other.app.token"},
        format="json",
    )
    assert foreign.status_code == 200
    assert foreign.data["status"] == "REJECTED"
    assert foreign.data["code"] == "invalid_token"
    assert AccessLog.all_objects.count() == 0

    monkeypatch.setattr(FaceAuthClient, "verify_token", lambda self, token: _identity())
    employee = _face_employee(acme)
    _credential(employee)

    def pending(node, command_type, payload, timeout=None):
        return dispatch_command(node, command_type, payload, timeout=0)

    monkeypatch.setattr("apps.integrations.faceauth.identify.dispatch_command", pending)
    with override_settings(FACE_IDENTIFY_TIMEOUT_SECONDS=0):
        offline = client.post(
            "/api/v1/kiosk/face-identify/",
            {"redirect_token": "offline.token.value"},
            format="json",
        )
    assert offline.data["status"] == "NODE_UNREACHABLE"
    assert offline.data["code"] == DenialReason.NODE_OFFLINE
    log = AccessLog.all_objects.get()
    assert log.status == "DENIED"
    assert log.method == "FACIAL"
    assert log.source == "cloud"
    assert log.denial_reason == DenialReason.NODE_OFFLINE
    assert log.employee_id == employee.id


def test_kiosk_of_one_organization_cannot_see_another(face_door, acme, globex, globex_node):
    from apps.access.models import Door

    _integration(acme)
    _integration(globex, app_id="app_globex", api_key="globex-secret")
    _kiosk, acme_kiosk, _token = _kiosk_client(acme, face_door)
    other_door = Door.all_objects.create(
        organization=globex,
        node=globex_node,
        name="Sur",
        relay_device_id="RELAY9",
        direction="IN",
        face_enabled=True,
    )
    hidden, _client, _plain = _kiosk_client(globex, other_door, name="Oculto")
    request = FaceIdentificationRequest.all_objects.create(
        organization=globex,
        kiosk=hidden,
        door=other_door,
        token_digest="a" * 64,
        status=FaceIdentificationRequest.Status.GRANTED,
    )
    Employee.all_objects.create(
        organization=globex,
        document_id="900",
        first_name="Bruno",
        last_name="Díaz",
        email="bruno@globex.test",
    )
    assert (
        acme_kiosk.get(f"/api/v1/kiosk/face-identify/{request.id}/").status_code == 404
    )
    lookup = acme_kiosk.post(
        "/api/v1/kiosk/employees/lookup/",
        {"document_id": "900"},
        format="json",
    )
    assert lookup.status_code == 404


def test_me_hides_the_api_key_and_reports_camera(face_door, acme):
    _integration(acme, allow_kiosk_self_enrollment=True)
    _kiosk, client, _token = _kiosk_client(acme, face_door)
    me = client.get("/api/v1/kiosk/me/")
    assert me.status_code == 200
    assert me.data["app_id"] == "app_acme"
    assert me.data["face_enabled"] is True
    assert SECRET not in str(me.data)
    beat = client.post(
        "/api/v1/kiosk/heartbeat/",
        {"camera_permission": "denied"},
        format="json",
    )
    assert beat.status_code == 200
    assert beat.data["camera_permission"] == "denied"


def test_face_identify_rejects_video_uploads(face_door, acme):
    _integration(acme)
    _kiosk, client, _token = _kiosk_client(acme, face_door)
    uploaded = SimpleUploadedFile("clip.webm", b"not-a-video", content_type="video/webm")
    response = client.post("/api/v1/kiosk/face-identify/", {"video": uploaded}, format="multipart")
    assert response.status_code == 415
    assert FaceIdentificationRequest.all_objects.count() == 0


def test_enrollment_complete_links_the_selected_employee(acme, acme_client, monkeypatch):
    _integration(acme)
    employee = _face_employee(acme)
    started = acme_client.post(f"/api/v1/employees/{employee.id}/face-enrollment-sessions/")
    assert started.status_code == 201
    monkeypatch.setattr(
        FaceAuthClient,
        "verify_token",
        lambda self, token: _identity(email="otra@acme.test"),
    )
    mismatch = acme_client.post(
        f"/api/v1/face-enrollment-sessions/{started.data['id']}/complete/",
        {"redirect_token": "bad.email.token"},
        format="json",
    )
    assert mismatch.status_code == 409
    assert mismatch.data["code"] == "email_mismatch"
    assert Credential.all_objects.count() == 0

    monkeypatch.setattr(FaceAuthClient, "verify_token", lambda self, token: _identity())
    done = acme_client.post(
        f"/api/v1/face-enrollment-sessions/{started.data['id']}/complete/",
        {"redirect_token": "good.email.token"},
        format="json",
    )
    assert done.status_code == 409
    session = FaceEnrollmentSession.all_objects.get(pk=started.data["id"])
    assert session.status == FaceEnrollmentSession.Status.REJECTED

    fresh = acme_client.post(f"/api/v1/employees/{employee.id}/face-enrollment-sessions/")
    completed = acme_client.post(
        f"/api/v1/face-enrollment-sessions/{fresh.data['id']}/complete/",
        {"redirect_token": "good.email.token"},
        format="json",
    )
    assert completed.status_code == 200
    credential = Credential.all_objects.get(employee=employee, is_active=True)
    assert credential.type == Credential.CredentialType.FACIAL
    assert credential.payload == str(FACE_USER)
    assert credential.source == Credential.Source.FACEAUTH


def test_enrollment_records_faceauth_failures_and_blocks_kiosk_without_flag(
    face_door, acme, acme_client
):
    _integration(acme, allow_kiosk_self_enrollment=False)
    employee = _face_employee(acme)
    started = acme_client.post(f"/api/v1/employees/{employee.id}/face-enrollment-sessions/")
    failed = acme_client.post(
        f"/api/v1/face-enrollment-sessions/{started.data['id']}/fail/",
        {"code": "email_taken", "message": "El correo ya existe"},
        format="json",
    )
    assert failed.status_code == 200
    assert failed.data["failure_code"] == "email_taken"
    _kiosk, client, _token = _kiosk_client(acme, face_door)
    denied = client.post(
        "/api/v1/kiosk/face-enrollment-sessions/",
        {"document_id": employee.document_id},
        format="json",
    )
    assert denied.status_code == 403


def test_revoking_a_facial_credential_queues_deletion(acme):
    employee = _face_employee(acme)
    credential = _credential(employee)
    assert FaceAuthPendingDeletion.all_objects.count() == 0
    credential.is_active = False
    credential.deleted_at = timezone.now()
    credential.save(update_fields=["is_active", "deleted_at", "updated_at"])
    queued = FaceAuthPendingDeletion.all_objects.get()
    assert queued.faceauth_user_id == FACE_USER
    assert queued.reason == "credential_revoked"
    employee.is_active = False
    employee.save(update_fields=["is_active", "updated_at"])
    assert FaceAuthPendingDeletion.all_objects.count() == 1


def test_panel_login_links_by_email_and_does_not_provision(acme, acme_admin, monkeypatch):
    _integration(acme, allow_panel_login=True)
    identity = _identity(email=acme_admin.email)
    monkeypatch.setattr(FaceAuthClient, "verify_token", lambda self, token: identity)
    client = APIClient()
    response = client.post(
        "/api/v1/auth/faceauth/callback/",
        {"redirect_token": "panel.token.value", "org_slug": "acme"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["access"]
    acme_admin.refresh_from_db()
    assert acme_admin.faceauth_user_id == FACE_USER

    monkeypatch.setattr(
        FaceAuthClient,
        "verify_token",
        lambda self, token: _identity(email="nadie@acme.test", user_id=uuid.uuid4()),
    )
    missing = client.post(
        "/api/v1/auth/faceauth/callback/",
        {"redirect_token": "panel.other.value", "org_slug": "acme"},
        format="json",
    )
    assert missing.status_code == 403
    assert User.objects.filter(email="nadie@acme.test").count() == 0


def test_hosted_login_url_uses_the_stable_callback(acme):
    _integration(acme, allow_panel_login=True)
    response = APIClient().get("/api/v1/auth/faceauth/start/?org_slug=acme")
    assert response.status_code == 200
    assert "redirect_uri=" in response.data["url"]
    assert response.data["url"].startswith("http://faceauth.test/login?")
    options = APIClient().get("/api/v1/auth/faceauth/options/?org_slug=acme")
    assert options.data["allow_panel_login"] is True
    assert SECRET not in str(options.data)


def test_expired_enrollment_session(acme, acme_client, monkeypatch):
    _integration(acme)
    employee = _face_employee(acme)
    started = acme_client.post(f"/api/v1/employees/{employee.id}/face-enrollment-sessions/")
    session = FaceEnrollmentSession.all_objects.get(pk=started.data["id"])
    session.expires_at = timezone.now() - timedelta(minutes=1)
    session.save(update_fields=["expires_at"])
    monkeypatch.setattr(FaceAuthClient, "verify_token", lambda self, token: _identity())
    response = acme_client.post(
        f"/api/v1/face-enrollment-sessions/{session.id}/complete/",
        {"redirect_token": "late.token.value"},
        format="json",
    )
    assert response.status_code == 409
    assert response.data["code"] == "session_expired"
    session.refresh_from_db()
    assert session.status == FaceEnrollmentSession.Status.EXPIRED


def test_lookup_returns_name_without_email(face_door, acme):
    _integration(acme)
    employee = _face_employee(acme)
    _kiosk, client, _token = _kiosk_client(acme, face_door)
    found = client.post(
        "/api/v1/kiosk/employees/lookup/",
        {"document_id": employee.document_id},
        format="json",
    )
    assert found.status_code == 200
    assert found.data["first_name"] == "Ana"
    assert found.data["has_email"] is True
    assert "email" not in found.data
    assert "ana@acme.test" not in str(found.data)


def test_viewer_cannot_test_the_connection(viewer_client, acme, monkeypatch):
    _integration(acme)

    def boom(self):
        raise AssertionError("no debe llamar a Face-Auth")

    monkeypatch.setattr(FaceAuthClient, "get_application", boom)
    response = viewer_client.post("/api/v1/faceauth-integration/test/")
    assert response.status_code == 403
    listed = viewer_client.get("/api/v1/faceauth-integration/metrics/")
    assert listed.status_code == 200


def test_duplicate_biometric_is_rejected(acme, acme_client, monkeypatch):
    _integration(acme)
    owner = _face_employee(acme, document_id="1", email="ana@acme.test")
    other = _face_employee(acme, document_id="2", email="otro@acme.test")
    _credential(owner)
    monkeypatch.setattr(
        FaceAuthClient,
        "verify_token",
        lambda self, token: _identity(email="otro@acme.test"),
    )
    started = acme_client.post(f"/api/v1/employees/{other.id}/face-enrollment-sessions/")
    response = acme_client.post(
        f"/api/v1/face-enrollment-sessions/{started.data['id']}/complete/",
        {"redirect_token": "dup.biometric.token"},
        format="json",
    )
    assert response.status_code == 409
    assert response.data["code"] == "duplicate_biometric"
    assert Credential.all_objects.filter(employee=other).count() == 0
    assert Membership.objects.filter(organization=acme).exists()
