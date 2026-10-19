import csv
import io

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.mixins import TenantWriteMixin
from apps.integrations.authentication import APITokenPrincipal
from apps.integrations.bulk import upsert_employees
from apps.integrations.faceauth.enrollment import begin_enrollment, enrollment_payload
from apps.integrations.faceauth.flow import FaceFlowError
from apps.integrations.serializers import EmployeeBulkSerializer
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


class EmployeeWritePermission(TenantRolePermission):
    """Escritura de empleados: rol OPERATOR/ADMIN o token employees:write."""

    def has_permission(self, request, view) -> bool:
        user = request.user
        if isinstance(user, APITokenPrincipal):
            action = getattr(view, "action", None)
            if request.method in ("GET", "HEAD", "OPTIONS") or action in {
                "list",
                "retrieve",
                "face_readiness_report",
            }:
                if user.has_scope("employees:read") or user.has_scope("employees:write"):
                    return True
                self.message = "El token no tiene el alcance employees:read."
                return False
            if user.has_scope("employees:write"):
                return True
            self.message = "El token no tiene el alcance employees:write."
            return False
        return super().has_permission(request, view)


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
    permission_classes = [IsAuthenticated, EmployeeWritePermission]
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
        if isinstance(request.user, APITokenPrincipal):
            return Response(
                {"detail": "El enrolamiento facial requiere un usuario del panel."},
                status=status.HTTP_403_FORBIDDEN,
            )
        employee = self.get_object()
        try:
            session = begin_enrollment(
                employee,
                started_by=FaceEnrollmentSession.StartedBy.USER,
                user=request.user,
            )
        except FaceFlowError as exc:
            body = {"detail": exc.detail, "code": exc.code}
            if getattr(exc, "issues", None):
                body["issues"] = exc.issues
            return Response(body, status=exc.status)
        return Response(enrollment_payload(session), status=201)

    @extend_schema(tags=["Empleados"], request=EmployeeBulkSerializer)
    @action(detail=False, methods=["post"], url_path="bulk")
    def bulk(self, request):
        if request.content_type and "text/csv" in request.content_type:
            text = request.body.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
        elif request.FILES.get("file"):
            uploaded = request.FILES["file"]
            text = uploaded.read().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
        else:
            incoming = EmployeeBulkSerializer(data=request.data)
            incoming.is_valid(raise_exception=True)
            rows = incoming.validated_data["employees"]
        if not rows:
            return Response({"detail": "No hay filas para importar."}, status=400)
        if len(rows) > 2000:
            return Response({"detail": "El lote máximo es de 2000 empleados."}, status=400)
        result = upsert_employees(rows)
        code = status.HTTP_200_OK if not result["errors"] else status.HTTP_207_MULTI_STATUS
        return Response(result, status=code)


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
