from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.mixins import TenantWriteMixin
from apps.common.secrets import generate_secret
from apps.integrations.faceauth.enrollment import enrollment_payload
from apps.integrations.faceauth.flow import FaceFlowError
from apps.kiosk.filters import FaceEnrollmentSessionFilter, KioskFilter
from apps.kiosk.models import FaceEnrollmentSession, Kiosk
from apps.kiosk.serializers import FaceEnrollmentSessionSerializer, KioskSerializer
from apps.tenants.models import Membership
from apps.tenants.permissions import TenantRolePermission


@extend_schema_view(
    list=extend_schema(tags=["Kioscos"]),
    retrieve=extend_schema(tags=["Kioscos"]),
    create=extend_schema(tags=["Kioscos"]),
    update=extend_schema(tags=["Kioscos"]),
    partial_update=extend_schema(tags=["Kioscos"]),
    destroy=extend_schema(tags=["Kioscos"]),
)
class KioskViewSet(TenantWriteMixin, viewsets.ModelViewSet):
    serializer_class = KioskSerializer
    permission_classes = [IsAuthenticated, TenantRolePermission]
    write_roles = {Membership.Role.ADMIN}
    search_fields = ["name"]
    ordering_fields = ["name", "created_at", "last_seen_at"]
    filterset_class = KioskFilter

    def get_queryset(self):
        return Kiosk.objects.select_related("door")

    @extend_schema(tags=["Kioscos"], request=None, responses=KioskSerializer)
    @action(detail=True, methods=["post"], url_path="regenerate-token")
    def regenerate_token(self, request, pk=None):
        kiosk = self.get_object()
        plain, digest = generate_secret()
        kiosk.kiosk_token_hash = digest
        kiosk.save(update_fields=["kiosk_token_hash", "updated_at"])
        kiosk.plaintext_kiosk_token = plain
        return Response(KioskSerializer(kiosk).data)


@extend_schema_view(
    list=extend_schema(tags=["Enrolamiento facial"]),
    retrieve=extend_schema(tags=["Enrolamiento facial"]),
)
class FaceEnrollmentSessionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = FaceEnrollmentSessionSerializer
    permission_classes = [IsAuthenticated, TenantRolePermission]
    filterset_class = FaceEnrollmentSessionFilter
    ordering_fields = ["created_at", "expires_at", "status"]

    def get_queryset(self):
        return FaceEnrollmentSession.objects.select_related("employee", "started_by_user")

    def retrieve(self, request, *args, **kwargs):
        session = self.get_object()
        try:
            return Response(enrollment_payload(session))
        except FaceFlowError as exc:
            return Response({"code": exc.code, "detail": exc.detail}, status=exc.status)
