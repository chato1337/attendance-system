from apps.accounts.models import User
from apps.accounts.tokens import issue_tokens
from apps.integrations.faceauth.client import FaceAuthClient, FaceAuthError
from apps.integrations.faceauth.flow import FaceFlowError, parse_user_id, require_integration
from apps.tenants.models import Membership, Organization


def panel_login(org_slug: str, redirect_token: str) -> dict:
    organization = Organization.objects.filter(slug=org_slug, is_active=True).first()
    if organization is None:
        raise FaceFlowError("unknown_organization", "Organización desconocida.", 404)
    integration = require_integration(organization.id)
    if not integration.allow_panel_login:
        raise FaceFlowError(
            "panel_login_disabled",
            "Esta organización no permite ingresar con rostro.",
            403,
        )
    token = (redirect_token or "").strip()
    if not token:
        raise FaceFlowError("invalid_token", "Token inválido.", 400)
    try:
        identity = FaceAuthClient(integration).verify_token(token)
    except FaceAuthError as exc:
        raise FaceFlowError(exc.code, exc.message, 401) from exc
    if identity.get("app_id") and identity["app_id"] != integration.app_id:
        raise FaceFlowError("invalid_token", "El token pertenece a otra aplicación.", 401)

    user = _match_user(identity)
    if user is None:
        raise FaceFlowError(
            "unknown_user",
            "No hay un usuario del panel vinculado a ese rostro.",
            403,
        )
    if (
        not user.is_superadmin
        and not Membership.objects.filter(user=user, organization=organization).exists()
    ):
        raise FaceFlowError(
            "unknown_user",
            "Ese usuario no pertenece a la organización.",
            403,
        )
    return issue_tokens(user, organization)


def _match_user(identity: dict) -> User | None:
    user_id = parse_user_id(identity["user_id"])
    linked = User.objects.filter(faceauth_user_id=user_id, is_active=True).first()
    if linked is not None:
        return linked
    email = str(identity.get("email") or "").strip()
    if not email:
        return None
    user = User.objects.filter(email__iexact=email, is_active=True).first()
    if user is None:
        return None
    if user.faceauth_user_id and user.faceauth_user_id != user_id:
        return None
    if user.faceauth_user_id is None:
        user.faceauth_user_id = user_id
        user.save(update_fields=["faceauth_user_id"])
    return user
