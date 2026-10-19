import base64
import json
import uuid
from urllib.parse import urlencode

from django.conf import settings

from apps.integrations.models import FaceAuthIntegration


class FaceFlowError(Exception):
    def __init__(self, code: str, detail: str, status: int, issues: list | None = None):
        self.code = code
        self.detail = detail
        self.status = status
        self.issues = issues or []
        super().__init__(detail)


class TokenAlreadyUsed(FaceFlowError):
    def __init__(self):
        super().__init__("token_already_used", "El token ya fue utilizado.", 409)


def integration_ready(integration: FaceAuthIntegration | None) -> bool:
    return bool(
        integration
        and integration.enabled
        and integration.app_id
        and integration.api_key
        and integration.api_url
    )


def load_integration(organization_id) -> FaceAuthIntegration | None:
    return FaceAuthIntegration.all_objects.filter(organization_id=organization_id).first()


def require_integration(organization_id) -> FaceAuthIntegration:
    integration = load_integration(organization_id)
    if not integration_ready(integration):
        raise FaceFlowError(
            "faceauth_disabled",
            "El reconocimiento facial no está habilitado para la organización.",
            409,
        )
    return integration


def token_fingerprint(token: str) -> tuple[str, str]:
    from apps.common.secrets import hash_secret

    digest = hash_secret(token)
    jti = ""
    parts = token.split(".")
    if len(parts) < 2:
        return digest, jti
    try:
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        jti = str(payload.get("jti") or "")[:64]
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        jti = ""
    return digest, jti


def parse_user_id(value) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise FaceFlowError("invalid_token", "user_id de Face-Auth inválido.", 401) from exc


def frontend_base() -> str:
    return settings.FRONTEND_URL.rstrip("/")


def hosted_redirect_uris() -> list[str]:
    base = frontend_base()
    return [
        f"{base}/auth/faceauth/return",
        f"{base}/kiosk/callback",
        f"{base}/enroll/faceauth/callback",
    ]


def cors_origins() -> list[str]:
    origins = list(settings.CORS_ALLOWED_ORIGINS)
    origin = frontend_base()
    if origin not in origins:
        origins.append(origin)
    return origins


def hosted_url(integration: FaceAuthIntegration, purpose: str) -> str:
    web = (integration.web_url or settings.FACEAUTH_WEB_URL).rstrip("/")
    path = "register" if purpose == "enroll" else "login"
    redirect = {
        "login": hosted_redirect_uris()[0],
        "kiosk": hosted_redirect_uris()[1],
        "enroll": hosted_redirect_uris()[2],
    }[purpose]
    query = urlencode({"app_id": integration.app_id, "redirect_uri": redirect})
    return f"{web}/{path}?{query}"
