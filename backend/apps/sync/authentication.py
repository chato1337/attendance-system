from django.utils import timezone
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.access.models import AccessNode
from apps.common.secrets import hash_secret
from apps.tenants.context import set_current_organization


class NodePrincipal:
    """Identidad de un nodo autenticado con su API key."""

    is_authenticated = True
    is_active = True
    is_anonymous = False
    is_superadmin = False

    def __init__(self, node: AccessNode):
        self.node = node
        self.pk = node.pk
        self.id = node.pk

    def __str__(self) -> str:
        return f"node:{self.node_id}"

    @property
    def node_id(self):
        return self.node.pk


def resolve_node(token: str) -> AccessNode | None:
    if not token or len(token) > 512:
        return None
    digest = hash_secret(token)
    node = (
        AccessNode.all_objects.select_related("organization")
        .filter(api_key_hash=digest, is_active=True, organization__is_active=True)
        .first()
    )
    if node is None:
        return None
    now = timezone.now()
    AccessNode.all_objects.filter(pk=node.pk).update(last_sync_at=now)
    node.last_sync_at = now
    return node


class NodeAPIKeyAuthentication(BaseAuthentication):
    """`Authorization: Bearer <node_api_key>`. Fija el tenant del nodo."""

    www_authenticate_realm = "edge"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header:
            return None
        scheme, _, token = header.partition(" ")
        if scheme != "Bearer" or not token:
            return None
        node = resolve_node(token.strip())
        if node is None:
            raise AuthenticationFailed("API key de nodo inválida.", code="invalid_node_key")
        set_current_organization(node.organization)
        request.organization = node.organization
        request.node = node
        return NodePrincipal(node), token.strip()

    def authenticate_header(self, request):
        return 'Bearer realm="edge"'


class NodeAPIKeyScheme(OpenApiAuthenticationExtension):
    target_class = "apps.sync.authentication.NodeAPIKeyAuthentication"
    name = "nodeApiKey"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "Node API key",
            "description": (
                "API key del nodo Edge. Se muestra una sola vez al crear o regenerar el nodo."
            ),
        }
