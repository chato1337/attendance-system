from datetime import timedelta

from django.conf import settings
from django.http import FileResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.mixins import TenantWriteMixin
from apps.reports.engine import attendance_queryset, calculate_attendance, summarize
from apps.reports.filters import AttendanceFilter, HolidayFilter, ScheduleFilter, ShiftFilter
from apps.reports.models import DailyAttendance, ExportJob, ExportStatus, Holiday, Schedule, Shift
from apps.reports.serializers import (
    DailyAttendanceSerializer,
    ExportCreateSerializer,
    ExportJobSerializer,
    HolidaySerializer,
    RecalculateSerializer,
    ReportFilterSerializer,
    ScheduleSerializer,
    ShiftSerializer,
    filters_payload,
)
from apps.reports.signing import unsign_export
from apps.reports.tasks import generate_export
from apps.tenants.context import get_current_organization
from apps.tenants.models import Membership
from apps.tenants.permissions import TenantRolePermission

WRITE_ROLES = {Membership.Role.ADMIN, Membership.Role.OPERATOR}
ALL_ROLES = WRITE_ROLES | {Membership.Role.VIEWER}


def _range_filters(data) -> dict:
    return {
        "date_from": data["date_from"],
        "date_to": data["date_to"],
        "department": data.get("department"),
        "employee": data.get("employee"),
        "site": data.get("site") or "",
        "status": data.get("status") or "",
    }


@extend_schema_view(
    list=extend_schema(tags=["Horarios"]),
    retrieve=extend_schema(tags=["Horarios"]),
    create=extend_schema(tags=["Horarios"]),
    update=extend_schema(tags=["Horarios"]),
    partial_update=extend_schema(tags=["Horarios"]),
    destroy=extend_schema(tags=["Horarios"]),
)
class ShiftViewSet(TenantWriteMixin, viewsets.ModelViewSet):
    serializer_class = ShiftSerializer
    permission_classes = [IsAuthenticated, TenantRolePermission]
    write_roles = WRITE_ROLES
    filterset_class = ShiftFilter
    search_fields = ["name"]
    ordering_fields = ["name", "start_time", "created_at"]

    def get_queryset(self):
        return Shift.objects.all()


@extend_schema_view(
    list=extend_schema(tags=["Horarios"]),
    retrieve=extend_schema(tags=["Horarios"]),
    create=extend_schema(tags=["Horarios"]),
    update=extend_schema(tags=["Horarios"]),
    partial_update=extend_schema(tags=["Horarios"]),
    destroy=extend_schema(tags=["Horarios"]),
)
class ScheduleViewSet(TenantWriteMixin, viewsets.ModelViewSet):
    serializer_class = ScheduleSerializer
    permission_classes = [IsAuthenticated, TenantRolePermission]
    write_roles = WRITE_ROLES
    filterset_class = ScheduleFilter
    ordering_fields = ["created_at", "updated_at"]

    def get_queryset(self):
        return Schedule.objects.select_related("shift", "employee", "department")


@extend_schema_view(
    list=extend_schema(tags=["Horarios"]),
    retrieve=extend_schema(tags=["Horarios"]),
    create=extend_schema(tags=["Horarios"]),
    update=extend_schema(tags=["Horarios"]),
    partial_update=extend_schema(tags=["Horarios"]),
    destroy=extend_schema(tags=["Horarios"]),
)
class HolidayViewSet(TenantWriteMixin, viewsets.ModelViewSet):
    serializer_class = HolidaySerializer
    permission_classes = [IsAuthenticated, TenantRolePermission]
    write_roles = WRITE_ROLES
    filterset_class = HolidayFilter
    search_fields = ["name"]
    ordering_fields = ["date", "name", "created_at"]

    def get_queryset(self):
        return Holiday.objects.all()

    def perform_destroy(self, instance):
        instance.delete()


@extend_schema_view(
    list=extend_schema(tags=["Reportes"]),
    retrieve=extend_schema(tags=["Reportes"]),
)
class AttendanceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DailyAttendanceSerializer
    permission_classes = [IsAuthenticated, TenantRolePermission]
    filterset_class = AttendanceFilter
    ordering_fields = ["work_date", "status", "employee__last_name", "worked_minutes"]

    def get_queryset(self):
        return DailyAttendance.objects.select_related("employee", "department")


class SummaryView(APIView):
    permission_classes = [IsAuthenticated, TenantRolePermission]

    @extend_schema(tags=["Reportes"], parameters=[ReportFilterSerializer])
    def get(self, request):
        incoming = ReportFilterSerializer(data=request.query_params)
        incoming.is_valid(raise_exception=True)
        filters = _range_filters(incoming.validated_data)
        queryset = attendance_queryset(get_current_organization(), filters)
        return Response(summarize(queryset, filters["date_from"], filters["date_to"]))


class RecalculateView(APIView):
    permission_classes = [IsAuthenticated, TenantRolePermission]
    write_roles = WRITE_ROLES

    @extend_schema(tags=["Reportes"], request=RecalculateSerializer)
    def post(self, request):
        incoming = RecalculateSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        data = incoming.validated_data
        rows = calculate_attendance(
            get_current_organization(),
            data["date_from"],
            data["date_to"],
        )
        return Response(
            {
                "rows": rows,
                "date_from": data["date_from"].isoformat(),
                "date_to": data["date_to"].isoformat(),
            }
        )


class ExportJobViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ExportJobSerializer
    permission_classes = [IsAuthenticated, TenantRolePermission]
    write_roles = ALL_ROLES
    ordering_fields = ["created_at"]

    def get_queryset(self):
        return ExportJob.objects.all()

    @extend_schema(
        tags=["Reportes"],
        request=ExportCreateSerializer,
        responses={202: ExportJobSerializer},
    )
    def create(self, request, *args, **kwargs):
        incoming = ExportCreateSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        data = incoming.validated_data
        job = ExportJob.objects.create(
            organization=get_current_organization(),
            requested_by=request.user,
            export_format=data["format"],
            status=ExportStatus.PENDING,
            filters=filters_payload(data),
            expires_at=timezone.now() + timedelta(seconds=settings.EXPORT_LINK_TTL_SECONDS),
        )
        generate_export.delay(str(job.id))
        job.refresh_from_db()
        return Response(ExportJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class ExportDownloadView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(tags=["Reportes"], responses={(200, "application/octet-stream"): bytes})
    def get(self, request, pk):
        if unsign_export(request.query_params.get("token", "")) != str(pk):
            return Response({"detail": "Enlace inválido o vencido."}, status=403)
        job = ExportJob.all_objects.filter(pk=pk).first()
        if job is None or job.status != ExportStatus.READY or not job.file:
            return Response({"detail": "El archivo no está listo."}, status=409)
        if job.expires_at < timezone.now():
            return Response({"detail": "El enlace expiró."}, status=403)
        filename = (
            f"asistencia-{job.filters.get('date_from', 'desde')}"
            f"-{job.filters.get('date_to', 'hasta')}.{job.export_format}"
        )
        return FileResponse(job.file.open("rb"), as_attachment=True, filename=filename)
