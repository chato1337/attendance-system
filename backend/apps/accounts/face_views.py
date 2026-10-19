from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integrations.faceauth.client import FaceAuthClient, FaceAuthError
from apps.integrations.faceauth.enrollment import remember_pending_identity
from apps.integrations.faceauth.flow import (
    FaceFlowError,
    hosted_url,
    integration_ready,
    load_integration,
    require_integration,
)
from apps.integrations.faceauth.login import panel_login
from apps.tenants.models import Organization


class FaceAuthOptionsView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(tags=["Face-Auth"], summary="Opciones públicas de login con rostro")
    def get(self, request):
        organization = Organization.objects.filter(
            slug=request.query_params.get("org_slug", ""),
            is_active=True,
        ).first()
        if organization is None:
            return Response({"allow_panel_login": False})
        integration = load_integration(organization.id)
        if not integration_ready(integration) or not integration.allow_panel_login:
            return Response({"allow_panel_login": False, "org_slug": organization.slug})
        return Response(
            {
                "allow_panel_login": True,
                "org_slug": organization.slug,
                "app_id": integration.app_id,
                "api_url": integration.api_url,
                "web_url": integration.web_url,
            }
        )


class FaceAuthCallbackView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(tags=["Face-Auth"], summary="Intercambiar redirect_token por JWT del panel")
    def post(self, request):
        try:
            tokens = panel_login(
                str(request.data.get("org_slug") or ""),
                str(request.data.get("redirect_token") or ""),
            )
        except FaceFlowError as exc:
            return Response({"code": exc.code, "detail": exc.detail}, status=exc.status)
        return Response(tokens)


class FaceAuthStartView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(tags=["Face-Auth"], summary="URL del SSO alojado para el login del panel")
    def get(self, request):
        organization = Organization.objects.filter(
            slug=request.query_params.get("org_slug", ""),
            is_active=True,
        ).first()
        if organization is None:
            return Response({"detail": "No encontrado."}, status=404)
        try:
            integration = require_integration(organization.id)
        except FaceFlowError as exc:
            return Response({"code": exc.code, "detail": exc.detail}, status=exc.status)
        if not integration.allow_panel_login:
            return Response(
                {
                    "code": "panel_login_disabled",
                    "detail": "El login con rostro no está habilitado.",
                },
                status=403,
            )
        return Response({"url": hosted_url(integration, "login")})


class FaceAuthPendingView(APIView):
    """Respaldo hosted: identidad que llegó sin una sesión de enrolamiento."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(tags=["Face-Auth"])
    def post(self, request):
        organization = Organization.objects.filter(
            slug=str(request.data.get("org_slug") or ""),
            is_active=True,
        ).first()
        if organization is None:
            return Response({"detail": "No encontrado."}, status=404)
        try:
            integration = require_integration(organization.id)
            token = str(request.data.get("redirect_token") or "")
            identity = FaceAuthClient(integration).verify_token(token)
            pending = remember_pending_identity(organization, identity)
        except FaceAuthError as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=401)
        except FaceFlowError as exc:
            return Response({"code": exc.code, "detail": exc.detail}, status=exc.status)
        return Response({"id": str(pending.id), "email": pending.email}, status=201)
