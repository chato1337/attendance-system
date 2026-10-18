from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts.serializers import (
    LoginSerializer,
    SwitchOrganizationSerializer,
    TenantTokenRefreshSerializer,
)
from apps.accounts.tokens import issue_tokens, resolve_role
from apps.tenants.models import Membership


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer

    @extend_schema(tags=["Autenticación"], summary="Obtener JWT")
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class RefreshView(TokenRefreshView):
    serializer_class = TenantTokenRefreshSerializer

    @extend_schema(tags=["Autenticación"], summary="Renovar access token")
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class SwitchOrganizationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Autenticación"],
        request=SwitchOrganizationSerializer,
        summary="Cambiar la organización activa",
    )
    def post(self, request):
        serializer = SwitchOrganizationSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        organization = serializer.validated_data["organization_id"]
        return Response(issue_tokens(request.user, organization))


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Autenticación"], summary="Usuario autenticado y sus membresías")
    def get(self, request):
        memberships = Membership.objects.filter(
            user=request.user,
            organization__is_active=True,
        ).select_related("organization")
        organization = getattr(request, "organization", None)
        return Response(
            {
                "id": request.user.id,
                "username": request.user.username,
                "email": request.user.email,
                "first_name": request.user.first_name,
                "last_name": request.user.last_name,
                "is_superadmin": request.user.is_superadmin,
                "organization_id": organization.id if organization else None,
                "role": resolve_role(request.user, organization) if organization else None,
                "memberships": [
                    {
                        "organization_id": item.organization_id,
                        "name": item.organization.name,
                        "slug": item.organization.slug,
                        "role": item.role,
                    }
                    for item in memberships
                ],
            }
        )
