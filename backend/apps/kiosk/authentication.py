from django.utils import timezone
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.accounts.authentication import TenantJWTAuthentication
from apps.common.secrets import hash_secret
from apps.kiosk.models import Kiosk
from apps.tenants.context import set_current_organization


class KioskPrincipal:
    is_authenticated = True
    is_active = True
    is_anonymous = False
    is_superadmin = False

    def __init__(self, kiosk: Kiosk):
        self.kiosk = kiosk
        self.pk = kiosk.pk
        self.id = kiosk.pk

    def __str__(self) -> str:
        return f"kiosk:{self.kiosk.pk}"


def find_kiosk(token: str) -> Kiosk | None:
    if not token or len(token) > 512:
        return None
    return (
        Kiosk.all_objects.select_related("door", "door__node", "organization")
        .filter(
            kiosk_token_hash=hash_secret(token),
            is_active=True,
            deleted_at__isnull=True,
            organization__is_active=True,
        )
        .first()
    )


def touch_kiosk(kiosk: Kiosk, camera_permission: str | None = None) -> None:
    now = timezone.now()
    fields = {"last_seen_at": now, "updated_at": now}
    if camera_permission in Kiosk.CameraPermission.values:
        fields["camera_permission"] = camera_permission
        kiosk.camera_permission = camera_permission
    Kiosk.all_objects.filter(pk=kiosk.pk).update(**fields)
    kiosk.last_seen_at = now


def _bind(request, kiosk: Kiosk, token: str):
    set_current_organization(kiosk.organization)
    request.organization = kiosk.organization
    request.kiosk = kiosk
    return KioskPrincipal(kiosk), token


class KioskTokenAuthentication(BaseAuthentication):
    """`Authorization: Bearer <kiosk_token>`."""

    www_authenticate_realm = "kiosk"

    def authenticate(self, request):
        token = _bearer(request)
        if token is None:
            return None
        kiosk = find_kiosk(token)
        if kiosk is None:
            raise AuthenticationFailed("Token de kiosco inválido.", code="invalid_kiosk_token")
        return _bind(request, kiosk, token)

    def authenticate_header(self, request):
        return 'Bearer realm="kiosk"'


class PanelOrKioskAuthentication(BaseAuthentication):
    """Acepta el token del kiosco o el JWT del panel."""

    def authenticate(self, request):
        token = _bearer(request)
        if token is not None:
            kiosk = find_kiosk(token)
            if kiosk is not None:
                return _bind(request, kiosk, token)
        return TenantJWTAuthentication().authenticate(request)

    def authenticate_header(self, request):
        return 'Bearer realm="kiosk"'


class KioskTokenScheme(OpenApiAuthenticationExtension):
    target_class = "apps.kiosk.authentication.KioskTokenAuthentication"
    name = "kioskToken"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "Kiosk token",
            "description": "Token del kiosco. Se muestra una sola vez al crearlo o regenerarlo.",
        }


def _bearer(request) -> str | None:
    header = request.headers.get("Authorization", "")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme != "Bearer" or not token.strip():
        return None
    return token.strip()
