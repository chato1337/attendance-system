from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access.filters import AccessAnomalyFilter, AccessLogFilter, DoorFilter, ReaderFilter
from apps.access.models import (
    AccessAnomaly,
    AccessLog,
    AccessNode,
    Door,
    Reader,
    ReaderProfile,
    Zone,
)
from apps.access.normalization import NormalizationError, apply_normalization, validate_steps
from apps.access.occupancy import occupancy_snapshot, reset_presence
from apps.access.serializers import (
    AccessAnomalySerializer,
    AccessLogSerializer,
    AccessNodeSerializer,
    DoorSerializer,
    OccupancyResetSerializer,
    ReaderProfilePreviewSerializer,
    ReaderProfileSerializer,
    ReaderSerializer,
    ZoneSerializer,
)
from apps.common.mixins import TenantWriteMixin
from apps.common.secrets import generate_secret
from apps.tenants.models import Membership
from apps.tenants.permissions import ALL_TENANT_ROLES, TenantRolePermission

OPERATIONAL = {Membership.Role.ADMIN, Membership.Role.OPERATOR}
ADMIN_ONLY = {Membership.Role.ADMIN}


def _validation_message(exc: DjangoValidationError) -> str:
    if getattr(exc, "messages", None):
        return " ".join(str(message) for message in exc.messages)
    return str(exc)


@extend_schema_view(
    list=extend_schema(tags=["Zonas"]),
    retrieve=extend_schema(tags=["Zonas"]),
    create=extend_schema(tags=["Zonas"]),
    update=extend_schema(tags=["Zonas"]),
    partial_update=extend_schema(tags=["Zonas"]),
    destroy=extend_schema(tags=["Zonas"]),
)
class ZoneViewSet(TenantWriteMixin, viewsets.ModelViewSet):
    serializer_class = ZoneSerializer
    permission_classes = [IsAuthenticated, TenantRolePermission]
    write_roles = OPERATIONAL
    search_fields = ["name"]
    ordering_fields = ["name", "version", "created_at"]
    filterset_fields = ["is_active"]

    def get_queryset(self):
        return Zone.objects.all()


@extend_schema_view(
    list=extend_schema(tags=["Perfiles de lector"]),
    retrieve=extend_schema(tags=["Perfiles de lector"]),
    create=extend_schema(tags=["Perfiles de lector"]),
    update=extend_schema(tags=["Perfiles de lector"]),
    partial_update=extend_schema(tags=["Perfiles de lector"]),
    destroy=extend_schema(tags=["Perfiles de lector"]),
)
class ReaderProfileViewSet(TenantWriteMixin, viewsets.ModelViewSet):
    serializer_class = ReaderProfileSerializer
    permission_classes = [IsAuthenticated, TenantRolePermission]
    write_roles = OPERATIONAL
    action_roles = {"preview": ALL_TENANT_ROLES}
    search_fields = ["name", "credential_type"]
    ordering_fields = ["name", "version", "credential_type"]
    filterset_fields = ["credential_type", "is_active"]

    def get_queryset(self):
        return ReaderProfile.objects.all()

    @extend_schema(
        tags=["Perfiles de lector"],
        request=ReaderProfilePreviewSerializer,
        responses={200: dict},
    )
    @action(detail=True, methods=["post"], url_path="preview")
    def preview(self, request, pk=None):
        profile = self.get_object()
        incoming = ReaderProfilePreviewSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        data = incoming.validated_data
        steps = data.get("normalization", profile.normalization)
        min_length = data.get("min_length", profile.min_length)
        max_length = data.get("max_length", profile.max_length)
        try:
            validate_steps(steps)
            payload = apply_normalization(
                data["sample"],
                steps,
                min_length=min_length,
                max_length=max_length,
            )
        except DjangoValidationError as exc:
            return Response({"ok": False, "error": _validation_message(exc)})
        except NormalizationError as exc:
            return Response({"ok": False, "error": exc.message})
        return Response({"ok": True, "payload": payload})


@extend_schema_view(
    list=extend_schema(tags=["Nodos"]),
    retrieve=extend_schema(tags=["Nodos"]),
    create=extend_schema(tags=["Nodos"]),
    update=extend_schema(tags=["Nodos"]),
    partial_update=extend_schema(tags=["Nodos"]),
    destroy=extend_schema(tags=["Nodos"]),
)
class AccessNodeViewSet(TenantWriteMixin, viewsets.ModelViewSet):
    serializer_class = AccessNodeSerializer
    permission_classes = [IsAuthenticated, TenantRolePermission]
    write_roles = ADMIN_ONLY
    search_fields = ["name", "site"]
    ordering_fields = ["name", "created_at", "last_heartbeat_at", "is_online"]
    filterset_fields = ["is_active", "is_online"]

    def get_queryset(self):
        return AccessNode.objects.all()

    @extend_schema(tags=["Nodos"], request=None, responses=AccessNodeSerializer)
    @action(detail=True, methods=["post"], url_path="regenerate-key")
    def regenerate_key(self, request, pk=None):
        node = self.get_object()
        plain, digest = generate_secret()
        node.api_key_hash = digest
        node.save(update_fields=["api_key_hash", "updated_at"])
        node.plaintext_api_key = plain
        return Response(AccessNodeSerializer(node).data)


@extend_schema_view(
    list=extend_schema(tags=["Puertas"]),
    retrieve=extend_schema(tags=["Puertas"]),
    create=extend_schema(tags=["Puertas"]),
    update=extend_schema(tags=["Puertas"]),
    partial_update=extend_schema(tags=["Puertas"]),
    destroy=extend_schema(tags=["Puertas"]),
)
class DoorViewSet(TenantWriteMixin, viewsets.ModelViewSet):
    serializer_class = DoorSerializer
    permission_classes = [IsAuthenticated, TenantRolePermission]
    write_roles = OPERATIONAL
    filterset_class = DoorFilter
    search_fields = ["name", "relay_device_id"]
    ordering_fields = ["name", "version", "direction"]

    def get_queryset(self):
        return Door.objects.select_related("node", "zone")


@extend_schema_view(
    list=extend_schema(tags=["Lectores"]),
    retrieve=extend_schema(tags=["Lectores"]),
    create=extend_schema(tags=["Lectores"]),
    update=extend_schema(tags=["Lectores"]),
    partial_update=extend_schema(tags=["Lectores"]),
    destroy=extend_schema(tags=["Lectores"]),
)
class ReaderViewSet(TenantWriteMixin, viewsets.ModelViewSet):
    serializer_class = ReaderSerializer
    permission_classes = [IsAuthenticated, TenantRolePermission]
    write_roles = OPERATIONAL
    filterset_class = ReaderFilter
    search_fields = ["name", "reader_device_id"]
    ordering_fields = ["name", "version", "reader_device_id"]

    def get_queryset(self):
        return Reader.objects.select_related("door", "door__node", "reader_profile")


@extend_schema_view(
    list=extend_schema(tags=["Marcaciones"]),
    retrieve=extend_schema(tags=["Marcaciones"]),
)
class AccessLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AccessLogSerializer
    permission_classes = [IsAuthenticated, TenantRolePermission]
    filterset_class = AccessLogFilter
    ordering_fields = ["timestamp", "status", "direction", "created_at"]

    def get_queryset(self):
        return AccessLog.objects.select_related("node", "door", "employee", "credential")


class OccupancyView(APIView):
    permission_classes = [IsAuthenticated, TenantRolePermission]
    read_roles = ALL_TENANT_ROLES

    @extend_schema(tags=["Aforo"], responses={200: dict})
    def get(self, request):
        return Response(occupancy_snapshot(request.organization))


class OccupancyResetView(APIView):
    permission_classes = [IsAuthenticated, TenantRolePermission]
    write_roles = OPERATIONAL

    @extend_schema(tags=["Aforo"], request=OccupancyResetSerializer, responses={200: dict})
    def post(self, request):
        incoming = OccupancyResetSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        data = incoming.validated_data
        reset = reset_presence(
            request.organization,
            employee_id=data.get("employee"),
            node_id=data.get("node"),
            actor_id=request.user.pk,
        )
        return Response({"reset": reset})


@extend_schema_view(
    list=extend_schema(tags=["Anomalías"]),
    retrieve=extend_schema(tags=["Anomalías"]),
)
class AccessAnomalyViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AccessAnomalySerializer
    permission_classes = [IsAuthenticated, TenantRolePermission]
    filterset_class = AccessAnomalyFilter
    ordering_fields = ["created_at", "kind"]

    def get_queryset(self):
        return AccessAnomaly.objects.select_related("node", "employee", "access_log")
