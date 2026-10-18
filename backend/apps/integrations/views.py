from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integrations.models import FaceAuthIntegration
from apps.integrations.serializers import FaceAuthIntegrationSerializer
from apps.tenants.context import get_current_organization
from apps.tenants.models import Membership
from apps.tenants.permissions import TenantRolePermission


class FaceAuthIntegrationView(APIView):
    permission_classes = [IsAuthenticated, TenantRolePermission]
    read_roles = {Membership.Role.ADMIN}
    write_roles = {Membership.Role.ADMIN}

    def _get_or_create(self) -> FaceAuthIntegration:
        organization = get_current_organization()
        integration, _created = FaceAuthIntegration.objects.get_or_create(
            organization=organization,
            defaults={
                "api_url": settings.FACEAUTH_API_URL,
                "web_url": settings.FACEAUTH_WEB_URL,
            },
        )
        return integration

    @extend_schema(tags=["Face-Auth"], responses=FaceAuthIntegrationSerializer)
    def get(self, request):
        integration = self._get_or_create()
        return Response(FaceAuthIntegrationSerializer(integration).data)

    @extend_schema(
        tags=["Face-Auth"],
        request=FaceAuthIntegrationSerializer,
        responses=FaceAuthIntegrationSerializer,
    )
    def patch(self, request):
        integration = self._get_or_create()
        serializer = FaceAuthIntegrationSerializer(integration, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
