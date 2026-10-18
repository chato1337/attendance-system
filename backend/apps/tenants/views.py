from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.tenants.context import get_current_organization
from apps.tenants.models import Membership, Organization
from apps.tenants.permissions import IsSuperAdmin, TenantRolePermission
from apps.tenants.serializers import MembershipSerializer, OrganizationSerializer


@extend_schema_view(
    list=extend_schema(tags=["Organizaciones"]),
    retrieve=extend_schema(tags=["Organizaciones"]),
    create=extend_schema(tags=["Organizaciones"]),
    update=extend_schema(tags=["Organizaciones"]),
    partial_update=extend_schema(tags=["Organizaciones"]),
    destroy=extend_schema(tags=["Organizaciones"]),
)
class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    search_fields = ["name", "slug"]
    ordering_fields = ["name", "created_at", "slug"]
    filterset_fields = ["is_active"]

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])


@extend_schema_view(
    list=extend_schema(tags=["Membresías"]),
    retrieve=extend_schema(tags=["Membresías"]),
    create=extend_schema(tags=["Membresías"]),
    update=extend_schema(tags=["Membresías"]),
    partial_update=extend_schema(tags=["Membresías"]),
    destroy=extend_schema(tags=["Membresías"]),
)
class MembershipViewSet(viewsets.ModelViewSet):
    serializer_class = MembershipSerializer
    permission_classes = [IsAuthenticated, TenantRolePermission]
    write_roles = {Membership.Role.ADMIN}
    search_fields = ["user__username", "user__email", "user__first_name", "user__last_name"]
    ordering_fields = ["created_at", "role", "user__username"]
    filterset_fields = ["role"]

    def get_queryset(self):
        return Membership.objects.filter(organization=get_current_organization()).select_related(
            "user",
            "organization",
        )

    def perform_create(self, serializer):
        serializer.save(organization=get_current_organization())

    def perform_destroy(self, instance):
        instance.delete()
