from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integrations.faceauth.client import FaceAuthClient, FaceAuthError
from apps.integrations.faceauth.flow import integration_ready
from apps.integrations.models import FaceAuthIntegration, FaceAuthPendingDeletion
from apps.integrations.serializers import FaceAuthIntegrationSerializer
from apps.kiosk.models import FaceIdentificationRequest, Kiosk
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


class FaceAuthTestConnectionView(APIView):
    permission_classes = [IsAuthenticated, TenantRolePermission]
    read_roles = {Membership.Role.ADMIN}
    write_roles = {Membership.Role.ADMIN}

    @extend_schema(tags=["Face-Auth"], request=None)
    def post(self, request):
        integration = FaceAuthIntegrationView()._get_or_create()
        if not integration.app_id or not integration.api_key:
            return Response(
                {"ok": False, "code": "not_configured", "detail": "Faltan app_id o api_key."},
                status=400,
            )
        try:
            application = FaceAuthClient(integration).get_application()
        except FaceAuthError as exc:
            return Response(
                {"ok": False, "code": exc.code, "detail": exc.message},
                status=exc.status_code if exc.status_code < 500 else 502,
            )
        return Response({"ok": True, "name": application.get("name") or integration.app_id})


class FaceAuthMetricsView(APIView):
    permission_classes = [IsAuthenticated, TenantRolePermission]
    read_roles = {Membership.Role.ADMIN, Membership.Role.OPERATOR, Membership.Role.VIEWER}

    @extend_schema(tags=["Face-Auth"])
    def get(self, request):
        organization = get_current_organization()
        since = timezone.now() - timedelta(hours=24)
        counts = {status: 0 for status in FaceIdentificationRequest.Status.values}
        codes: dict[str, int] = {}
        samples: list[int] = []
        rows = FaceIdentificationRequest.all_objects.filter(
            organization=organization,
            created_at__gte=since,
        ).only("status", "code", "timings")
        for row in rows:
            counts[row.status] = counts.get(row.status, 0) + 1
            if row.code:
                codes[row.code] = codes.get(row.code, 0) + 1
            verify_ms = (row.timings or {}).get("verify_ms")
            if isinstance(verify_ms, int):
                samples.append(verify_ms)
        cameras: dict[str, int] = {}
        for permission in Kiosk.all_objects.filter(organization=organization).values_list(
            "camera_permission", flat=True
        ):
            cameras[permission] = cameras.get(permission, 0) + 1
        samples.sort()
        p95 = samples[min(len(samples) - 1, int(len(samples) * 0.95))] if samples else None
        return Response(
            {
                "window_hours": 24,
                "identifications": counts,
                "codes": codes,
                "verify_ms_p95": p95,
                "camera_permission": cameras,
                "pending_deletions": FaceAuthPendingDeletion.all_objects.filter(
                    organization=organization,
                    processed_at__isnull=True,
                ).count(),
                "enabled": integration_ready(
                    FaceAuthIntegration.all_objects.filter(organization=organization).first()
                ),
            }
        )
