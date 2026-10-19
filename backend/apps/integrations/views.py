from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.mixins import TenantWriteMixin
from apps.common.secrets import generate_secret
from apps.integrations.authentication import APITokenPrincipal
from apps.integrations.faceauth.client import FaceAuthClient, FaceAuthError
from apps.integrations.faceauth.flow import integration_ready
from apps.integrations.models import (
    APIToken,
    FaceAuthIntegration,
    FaceAuthPendingDeletion,
    WebhookDelivery,
    WebhookSubscription,
)
from apps.integrations.serializers import (
    APITokenSerializer,
    FaceAuthIntegrationSerializer,
    WebhookDeliverySerializer,
    WebhookSubscriptionSerializer,
    WebhookTestSerializer,
)
from apps.integrations.webhooks import resend_delivery, sample_payload
from apps.kiosk.models import FaceIdentificationRequest, Kiosk
from apps.tenants.context import get_current_organization
from apps.tenants.models import Membership
from apps.tenants.permissions import TenantRolePermission

ADMIN_ONLY = {Membership.Role.ADMIN}


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


class WebhookAdminPermission(TenantRolePermission):
    """ADMIN del panel o token con alcance webhooks:manage."""

    def has_permission(self, request, view) -> bool:
        user = request.user
        if isinstance(user, APITokenPrincipal):
            if not user.has_scope("webhooks:manage"):
                self.message = "El token no tiene el alcance webhooks:manage."
                return False
            return True
        return super().has_permission(request, view)


@extend_schema_view(
    list=extend_schema(tags=["Webhooks"]),
    retrieve=extend_schema(tags=["Webhooks"]),
    create=extend_schema(tags=["Webhooks"]),
    update=extend_schema(tags=["Webhooks"]),
    partial_update=extend_schema(tags=["Webhooks"]),
    destroy=extend_schema(tags=["Webhooks"]),
)
class WebhookSubscriptionViewSet(TenantWriteMixin, viewsets.ModelViewSet):
    serializer_class = WebhookSubscriptionSerializer
    permission_classes = [IsAuthenticated, WebhookAdminPermission]
    write_roles = ADMIN_ONLY
    read_roles = ADMIN_ONLY
    search_fields = ["name", "url"]
    ordering_fields = ["name", "created_at", "updated_at"]

    def get_queryset(self):
        return WebhookSubscription.objects.all()

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])

    @extend_schema(tags=["Webhooks"], responses=WebhookDeliverySerializer(many=True))
    @action(detail=True, methods=["get"], url_path="deliveries")
    def deliveries(self, request, pk=None):
        subscription = self.get_object()
        queryset = WebhookDelivery.objects.filter(subscription=subscription).order_by("-created_at")
        page = self.paginate_queryset(queryset)
        serializer = WebhookDeliverySerializer(page or queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @extend_schema(
        tags=["Webhooks"],
        request=WebhookTestSerializer,
        responses={202: WebhookDeliverySerializer},
    )
    @action(detail=True, methods=["post"], url_path="test")
    def send_test(self, request, pk=None):
        subscription = self.get_object()
        incoming = WebhookTestSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        event = incoming.validated_data["event"]
        if event not in (subscription.events or []):
            return Response(
                {"detail": "La suscripción no escucha ese evento."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = sample_payload(subscription.organization_id, event)
        from apps.integrations.models import WebhookDeliveryStatus
        from apps.integrations.webhooks import _schedule

        delivery = WebhookDelivery.objects.create(
            organization=subscription.organization,
            subscription=subscription,
            event=event,
            payload=payload,
            status=WebhookDeliveryStatus.PENDING,
            next_retry_at=timezone.now(),
        )
        transaction.on_commit(lambda: _schedule(str(delivery.id), 0))
        return Response(WebhookDeliverySerializer(delivery).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(tags=["Webhooks"], responses=WebhookSubscriptionSerializer)
    @action(detail=True, methods=["post"], url_path="regenerate-secret")
    def regenerate_secret(self, request, pk=None):
        subscription = self.get_object()
        plain, _digest = generate_secret()
        subscription.secret = plain
        subscription.save(update_fields=["secret", "updated_at"])
        data = WebhookSubscriptionSerializer(subscription).data
        data["secret_value"] = plain
        return Response(data)


@extend_schema_view(
    list=extend_schema(tags=["Webhooks"]),
    retrieve=extend_schema(tags=["Webhooks"]),
)
class WebhookDeliveryViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = WebhookDeliverySerializer
    permission_classes = [IsAuthenticated, WebhookAdminPermission]
    read_roles = ADMIN_ONLY
    write_roles = ADMIN_ONLY
    ordering_fields = ["created_at", "status", "attempt"]
    filterset_fields = ["status", "event", "subscription"]

    def get_queryset(self):
        return WebhookDelivery.objects.select_related("subscription")

    @extend_schema(tags=["Webhooks"], responses={202: WebhookDeliverySerializer})
    @action(detail=True, methods=["post"], url_path="resend")
    def resend(self, request, pk=None):
        delivery = self.get_object()
        clone = resend_delivery(delivery)
        return Response(WebhookDeliverySerializer(clone).data, status=status.HTTP_202_ACCEPTED)


@extend_schema_view(
    list=extend_schema(tags=["Tokens de API"]),
    retrieve=extend_schema(tags=["Tokens de API"]),
    create=extend_schema(tags=["Tokens de API"]),
    destroy=extend_schema(tags=["Tokens de API"]),
)
class APITokenViewSet(
    TenantWriteMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = APITokenSerializer
    permission_classes = [IsAuthenticated, TenantRolePermission]
    write_roles = ADMIN_ONLY
    read_roles = ADMIN_ONLY
    search_fields = ["name", "token_prefix"]
    ordering_fields = ["created_at", "name"]

    def get_queryset(self):
        return APIToken.objects.all()

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])

    def create(self, request, *args, **kwargs):
        if isinstance(request.user, APITokenPrincipal):
            return Response(
                {"detail": "Cree tokens desde el panel con un usuario administrador."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().create(request, *args, **kwargs)
