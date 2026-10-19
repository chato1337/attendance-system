from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.mixins import TenantWriteMixin
from apps.integrations.faceauth.enrollment import begin_enrollment, enrollment_payload
from apps.integrations.faceauth.flow import FaceFlowError
from apps.kiosk.models import FaceEnrollmentSession
from apps.kiosk.serializers import FaceEnrollmentSessionSerializer
from apps.people.face import face_readiness
from apps.people.filters import CredentialFilter, EmployeeFilter
from apps.people.models import Credential, Department, Employee
from apps.people.serializers import (
    CredentialSerializer,
    DepartmentSerializer,
    EmployeeSerializer,
    FaceReadinessSerializer,
)
from apps.tenants.models import Membership
from apps.tenants.permissions import TenantRolePermission

WRITE_ROLES = {Membership.Role.ADMIN, Membership.Role.OPERATOR}


@extend_schema_view(
    list=extend_schema(tags=["Departamentos"]),
    retrieve=extend_schema(tags=["Departamentos"]),
    create=extend_schema(tags=["Departamentos"]),
    update=extend_schema(tags=["Departamentos"]),
    partial_update=extend_schema(tags=["Departamentos"]),
    destroy=extend_schema(tags=["Departamentos"]),
)
class DepartmentViewSet(TenantWriteMixin, viewsets.ModelViewSet):
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated, TenantRolePermission]
    write_roles = WRITE_ROLES
    search_fields = ["name"]
    ordering_fields = ["name", "version", "created_at"]
    filterset_fields = ["is_active"]

    def get_queryset(self):
        return Department.objects.all()


@extend_schema_view(
    list=extend_schema(tags=["Empleados"]),
    retrieve=extend_schema(tags=["Empleados"]),
    create=extend_schema(tags=["Empleados"]),
    update=extend_schema(tags=["Empleados"]),
    partial_update=extend_schema(tags=["Empleados"]),
    destroy=extend_schema(tags=["Empleados"]),
)
class EmployeeViewSet(TenantWriteMixin, viewsets.ModelViewSet):
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated, TenantRolePermission]
    write_roles = WRITE_ROLES
    filterset_class = EmployeeFilter
    search_fields = ["document_id", "first_name", "last_name", "email"]
    ordering_fields = ["last_name", "first_name", "document_id", "created_at", "version"]

    def get_queryset(self):
        return Employee.objects.select_related("department")

    @extend_schema(tags=["Empleados"], responses=FaceReadinessSerializer(many=True))
    @action(detail=False, methods=["get"], url_path="face-readiness")
    def face_readiness_report(self, request):
        report = face_readiness(list(self.get_queryset()))
        return Response(
            {"count": len(report), "results": FaceReadinessSerializer(report, many=True).data}
        )

    @extend_schema(
        tags=["Empleados"],
        request=None,
        responses={201: FaceEnrollmentSessionSerializer},
    )
    @action(detail=True, methods=["post"], url_path="face-enrollment-sessions")
    def start_face_enrollment(self, request, pk=None):
        employee = self.get_object()
        try:
            session = begin_enrollment(
                employee,
                started_by=FaceEnrollmentSession.StartedBy.USER,
                user=request.user,
            )
        except FaceFlowError as exc:
            body = {"detail": exc.detail, "code": exc.code}
            if exc.issues:
                body["issues"] = exc.issues
            return Response(body, status=exc.status)
        return Response(enrollment_payload(session), status=201)


@extend_schema_view(
    list=extend_schema(tags=["Credenciales"]),
    retrieve=extend_schema(tags=["Credenciales"]),
    create=extend_schema(tags=["Credenciales"]),
    update=extend_schema(tags=["Credenciales"]),
    partial_update=extend_schema(tags=["Credenciales"]),
    destroy=extend_schema(tags=["Credenciales"]),
)
class CredentialViewSet(TenantWriteMixin, viewsets.ModelViewSet):
    serializer_class = CredentialSerializer
    permission_classes = [IsAuthenticated, TenantRolePermission]
    write_roles = WRITE_ROLES
    filterset_class = CredentialFilter
    search_fields = ["payload"]
    ordering_fields = ["version", "created_at", "type"]

    def get_queryset(self):
        return Credential.objects.select_related("employee", "reader_profile")
