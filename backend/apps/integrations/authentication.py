from types import SimpleNamespace

from django.utils import timezone
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.common.secrets import hash_secret
from apps.integrations.models import APIToken
from apps.tenants.context import set_current_organization
from apps.tenants.models import Membership

TOKEN_PREFIX = "atk_"


class APITokenPrincipal:
    """Identidad de un token de integración (sin usuario de panel)."""

    is_authenticated = True
    is_active = True
    is_anonymous = False
    is_superadmin = False

    def __init__(self, token: APIToken):
        self.token = token
        self.pk = token.pk
        self.id = token.pk
        self.scopes = list(token.scopes or [])

    def __str__(self) -> str:
        return f"api-token:{self.token.token_prefix}"

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


def role_for_scopes(scopes: list[str]) -> str:
    if "employees:write" in scopes or "webhooks:manage" in scopes:
        return Membership.Role.ADMIN
    if "employees:read" in scopes:
        return Membership.Role.VIEWER
    return Membership.Role.VIEWER


def resolve_api_token(raw: str) -> APIToken | None:
    if not raw or not raw.startswith(TOKEN_PREFIX) or len(raw) > 512:
        return None
    digest = hash_secret(raw)
    token = (
        APIToken.all_objects.select_related("organization")
        .filter(token_hash=digest, is_active=True, organization__is_active=True)
        .first()
    )
    if token is None:
        return None
    if token.expires_at and token.expires_at < timezone.now():
        return None
    return token


class OrgAPITokenAuthentication(BaseAuthentication):
    """`Authorization: Bearer atk_…`. Solo tokens con prefijo; el JWT sigue después."""

    www_authenticate_realm = "api-token"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header:
            return None
        scheme, _, token = header.partition(" ")
        if scheme != "Bearer" or not token.startswith(TOKEN_PREFIX):
            return None
        api_token = resolve_api_token(token.strip())
        if api_token is None:
            raise AuthenticationFailed("Token de API inválido o vencido.", code="invalid_api_token")
        organization = api_token.organization
        set_current_organization(organization)
        request.organization = organization
        request.membership = SimpleNamespace(
            organization=organization,
            organization_id=organization.id,
            role=role_for_scopes(api_token.scopes or []),
        )
        request.api_token = api_token
        APIToken.all_objects.filter(pk=api_token.pk).update(last_used_at=timezone.now())
        return APITokenPrincipal(api_token), token.strip()

    def authenticate_header(self, request):
        return 'Bearer realm="api-token"'


class OrgAPITokenScheme(OpenApiAuthenticationExtension):
    target_class = "apps.integrations.authentication.OrgAPITokenAuthentication"
    name = "orgApiToken"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "atk_…",
            "description": (
                "Token de integración de la organización. Se muestra una sola vez al crearlo. "
                "Alcances: employees:read, employees:write, webhooks:manage."
            ),
        }
