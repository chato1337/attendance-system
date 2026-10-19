from django.utils import timezone

from apps.integrations.faceauth.client import FaceAuthClient, FaceAuthError
from apps.integrations.faceauth.flow import FaceFlowError, parse_user_id, require_integration
from apps.integrations.models import PendingFaceIdentity
from apps.kiosk.models import FaceEnrollmentSession, Kiosk
from apps.people.face import enrollment_blockers
from apps.people.models import Credential, Employee
from apps.tenants.models import Membership


def begin_enrollment(employee: Employee, *, started_by: str, user=None, kiosk: Kiosk | None = None):
    blockers = enrollment_blockers(employee)
    if blockers:
        raise FaceFlowError(
            "not_ready",
            "El empleado no está listo para enrolar el rostro.",
            400,
            blockers,
        )
    require_integration(employee.organization_id)
    return FaceEnrollmentSession.objects.create(
        organization=employee.organization,
        employee=employee,
        started_by=started_by,
        started_by_user=user,
        started_by_kiosk=kiosk,
    )


def enrollment_payload(session: FaceEnrollmentSession) -> dict:
    from apps.kiosk.serializers import FaceEnrollmentSessionSerializer

    integration = require_integration(session.organization_id)
    employee = session.employee
    data = FaceEnrollmentSessionSerializer(session).data
    data.update(
        {
            "app_id": integration.app_id,
            "api_url": integration.api_url,
            "web_url": integration.web_url,
            "email": employee.email,
            "first_name": employee.first_name,
            "last_name": employee.last_name,
        }
    )
    return data


def authorize_session(request, session: FaceEnrollmentSession) -> None:
    kiosk = getattr(request, "kiosk", None)
    if kiosk is not None:
        if (
            session.organization_id != kiosk.organization_id
            or session.started_by != FaceEnrollmentSession.StartedBy.KIOSK
            or session.started_by_kiosk_id != kiosk.id
        ):
            raise FaceFlowError("not_found", "No encontrado.", 404)
        return
    organization = getattr(request, "organization", None)
    if organization is None or session.organization_id != organization.id:
        raise FaceFlowError("not_found", "No encontrado.", 404)
    if request.user.is_superadmin:
        return
    membership = getattr(request, "membership", None)
    allowed = {Membership.Role.ADMIN, Membership.Role.OPERATOR}
    if membership is None or membership.role not in allowed:
        raise FaceFlowError("forbidden", "No puede completar el enrolamiento.", 403)


def load_session(session_id) -> FaceEnrollmentSession:
    session = (
        FaceEnrollmentSession.all_objects.select_related("employee", "organization")
        .filter(pk=session_id)
        .first()
    )
    if session is None:
        raise FaceFlowError("not_found", "No encontrado.", 404)
    return session


def complete_enrollment(
    session: FaceEnrollmentSession, redirect_token: str
) -> FaceEnrollmentSession:
    _open_session(session)
    integration = require_integration(session.organization_id)
    token = (redirect_token or "").strip()
    if not token:
        raise FaceFlowError("invalid_token", "Token inválido.", 400)
    client = FaceAuthClient(integration)
    try:
        identity = client.verify_token(token)
    except FaceAuthError as exc:
        session.status = FaceEnrollmentSession.Status.REJECTED
        session.failure_code = exc.code
        session.detail = {"message": exc.message}
        session.save(update_fields=["status", "failure_code", "detail"])
        raise FaceFlowError(exc.code, exc.message, 401) from exc

    if identity.get("app_id") and identity["app_id"] != integration.app_id:
        session.status = FaceEnrollmentSession.Status.REJECTED
        session.failure_code = "invalid_token"
        session.save(update_fields=["status", "failure_code"])
        raise FaceFlowError("invalid_token", "El token pertenece a otra aplicación.", 401)

    email = str(identity.get("email") or "").strip().lower()
    expected = (session.employee.email or "").strip().lower()
    if not email or email != expected:
        session.status = FaceEnrollmentSession.Status.REJECTED
        session.failure_code = "email_mismatch"
        session.detail = {"email": email}
        session.save(update_fields=["status", "failure_code", "detail"])
        raise FaceFlowError(
            "email_mismatch",
            "El correo verificado no coincide con el del empleado.",
            409,
        )

    user_id = parse_user_id(identity["user_id"])
    conflict = (
        Credential.all_objects.filter(
            organization_id=session.organization_id,
            type=Credential.CredentialType.FACIAL,
            payload=str(user_id),
            is_active=True,
        )
        .exclude(employee_id=session.employee_id)
        .exists()
    )
    if conflict:
        session.status = FaceEnrollmentSession.Status.REJECTED
        session.failure_code = "duplicate_biometric"
        session.save(update_fields=["status", "failure_code"])
        raise FaceFlowError(
            "duplicate_biometric",
            "Ese rostro ya está enrolado en otro empleado.",
            409,
        )

    _replace_facial_credential(session.employee, str(user_id))
    session.status = FaceEnrollmentSession.Status.COMPLETED
    session.faceauth_user_id = user_id
    session.failure_code = ""
    session.save(update_fields=["status", "faceauth_user_id", "failure_code"])
    return session


def fail_enrollment(
    session: FaceEnrollmentSession, code: str, message: str
) -> FaceEnrollmentSession:
    _open_session(session)
    session.status = FaceEnrollmentSession.Status.FAILED
    session.failure_code = (code or "failed")[:64]
    session.detail = {"message": (message or "")[:500]}
    session.save(update_fields=["status", "failure_code", "detail"])
    return session


def remember_pending_identity(organization, identity: dict) -> PendingFaceIdentity:
    user_id = parse_user_id(identity["user_id"])
    return PendingFaceIdentity.all_objects.create(
        organization=organization,
        faceauth_user_id=user_id,
        email=str(identity.get("email") or "")[:254],
        claims={
            "first_name": identity.get("first_name") or "",
            "last_name": identity.get("last_name") or "",
            "app_id": identity.get("app_id") or "",
        },
    )


def _open_session(session: FaceEnrollmentSession) -> None:
    if session.status != FaceEnrollmentSession.Status.PENDING:
        raise FaceFlowError("session_closed", "La sesión ya no está pendiente.", 409)
    if session.expires_at <= timezone.now():
        session.status = FaceEnrollmentSession.Status.EXPIRED
        session.save(update_fields=["status"])
        raise FaceFlowError("session_expired", "La sesión de enrolamiento expiró.", 409)


def _replace_facial_credential(employee: Employee, payload: str) -> Credential:
    now = timezone.now()
    previous = Credential.all_objects.filter(
        employee=employee,
        type=Credential.CredentialType.FACIAL,
        is_active=True,
    ).exclude(payload=payload)
    for credential in previous:
        credential.is_active = False
        credential.deleted_at = now
        credential.save(update_fields=["is_active", "deleted_at", "updated_at"])
    current = Credential.all_objects.filter(
        employee=employee,
        type=Credential.CredentialType.FACIAL,
        payload=payload,
        is_active=True,
    ).first()
    if current is not None:
        return current
    return Credential.all_objects.create(
        organization=employee.organization,
        employee=employee,
        type=Credential.CredentialType.FACIAL,
        payload=payload,
        source=Credential.Source.FACEAUTH,
    )
