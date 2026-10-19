import uuid

from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access.models import AccessNode, Reader
from apps.accounts.authentication import TenantJWTAuthentication
from apps.sync.authentication import NodeAPIKeyAuthentication
from apps.sync.commands import (
    CommandExpired,
    CommandValidationError,
    acknowledge,
    command_body,
    dispatch_command,
    poll_commands,
)
from apps.sync.delta import build_delta
from apps.sync.formatting import isoformat
from apps.sync.heartbeat import record_heartbeat
from apps.sync.ingestion import ingest_logs
from apps.sync.models import EdgeCommand, EnrollmentRead
from apps.sync.serializers import (
    AckSerializer,
    DispatchCommandSerializer,
    EnrollmentReadPanelSerializer,
    EnrollmentReadSerializer,
    HeartbeatSerializer,
    LogBatchSerializer,
)
from apps.sync.signals import enrollment_read_created
from apps.sync.throttles import EdgeNodeThrottle
from apps.tenants.models import Membership
from apps.tenants.permissions import ALL_TENANT_ROLES, TenantRolePermission

OPERATIONAL = {Membership.Role.ADMIN, Membership.Role.OPERATOR}
EDGE = {"tags": ["Protocolo Edge"]}


class EdgeAPIView(APIView):
    authentication_classes = [NodeAPIKeyAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [EdgeNodeThrottle]


class DeltaView(EdgeAPIView):
    @extend_schema(summary="Delta de sincronización", responses={200: dict}, **EDGE)
    def get(self, request):
        since, limit, error = _delta_params(request)
        if error:
            return error
        return Response(build_delta(request.node, since, limit))


class LogBatchView(EdgeAPIView):
    @extend_schema(
        summary="Lote de marcaciones",
        request=LogBatchSerializer,
        responses={200: dict},
        **EDGE,
    )
    def post(self, request):
        incoming = LogBatchSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        node_id = incoming.validated_data.get("node_id")
        if node_id and node_id != request.node.id:
            return Response(
                {"detail": "node_id no corresponde al nodo autenticado."},
                status=400,
            )
        return Response(ingest_logs(request.node, incoming.validated_data["logs"]))


class HeartbeatView(EdgeAPIView):
    @extend_schema(
        summary="Latido del nodo",
        request=HeartbeatSerializer,
        responses={200: dict},
        **EDGE,
    )
    def post(self, request):
        incoming = HeartbeatSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        return Response(record_heartbeat(request.node, incoming.validated_data))


class CommandPollView(EdgeAPIView):
    @extend_schema(summary="Long-poll de comandos", responses={200: dict}, **EDGE)
    def get(self, request):
        wait, error = _wait_param(request)
        if error:
            return error
        commands = poll_commands(request.node, wait)
        return Response(
            {
                "server_time": isoformat(timezone.now()),
                "commands": [command_body(command) for command in commands],
            }
        )


class CommandAckView(EdgeAPIView):
    @extend_schema(
        summary="Confirmación de comando",
        request=AckSerializer,
        responses={200: dict},
        **EDGE,
    )
    def post(self, request, command_id):
        incoming = AckSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        try:
            command = acknowledge(request.node, command_id, incoming.validated_data["result"])
        except EdgeCommand.DoesNotExist:
            return Response({"detail": "No encontrado."}, status=404)
        except CommandExpired as exc:
            return Response(
                {"detail": "El comando expiró.", "status": exc.command.status},
                status=409,
            )
        except CommandValidationError as exc:
            return Response({"detail": exc.detail}, status=400)
        return Response(command_body(command))


class EnrollmentReadView(EdgeAPIView):
    @extend_schema(
        summary="Lectura de enrolamiento asistido",
        request=EnrollmentReadSerializer,
        responses={201: dict},
        **EDGE,
    )
    def post(self, request):
        incoming = EnrollmentReadSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        data = incoming.validated_data
        reader = (
            Reader.all_objects.filter(
                pk=data["reader_id"],
                organization=request.node.organization,
                door__node=request.node,
            )
            .select_related("door")
            .first()
        )
        if reader is None:
            return Response({"detail": "El lector no pertenece al nodo."}, status=400)
        command = None
        command_id = data.get("command_id")
        if command_id is not None:
            command = EdgeCommand.all_objects.filter(
                pk=command_id,
                node=request.node,
                type=EdgeCommand.Type.ENROLLMENT_MODE,
            ).first()
            if command is None:
                return Response({"detail": "El comando no pertenece al nodo."}, status=400)
        row = EnrollmentRead.all_objects.create(
            organization=request.node.organization,
            node=request.node,
            reader=reader,
            command=command,
            raw=data["raw"],
            payload=data.get("payload") or "",
            credential_type=data.get("credential_type") or "",
            error=data.get("error") or "",
        )
        enrollment_read_created.send(
            sender=EnrollmentRead,
            read=row,
            node_id=request.node.pk,
        )
        return Response({"id": str(row.id)}, status=201)


class EnrollmentReadListView(APIView):
    """Lecturas del enrolamiento asistido, para el panel."""

    authentication_classes = [TenantJWTAuthentication]
    permission_classes = [IsAuthenticated, TenantRolePermission]
    read_roles = ALL_TENANT_ROLES

    @extend_schema(
        summary="Lecturas de enrolamiento asistido",
        operation_id="enrollment_reads_list",
        responses={200: EnrollmentReadPanelSerializer(many=True)},
        tags=["Nodos"],
    )
    def get(self, request):
        reader_id, reader_error = _optional_uuid(request.query_params.get("reader"), "reader")
        if reader_error:
            return reader_error
        command_id, command_error = _optional_uuid(request.query_params.get("command"), "command")
        if command_error:
            return command_error
        queryset = EnrollmentRead.objects.order_by("-created_at")
        if reader_id is not None:
            queryset = queryset.filter(reader_id=reader_id)
        if command_id is not None:
            queryset = queryset.filter(command_id=command_id)
        rows = queryset[:100]
        return Response(EnrollmentReadPanelSerializer(rows, many=True).data)


class NodeCommandView(APIView):
    """Despacho y consulta de comandos desde el panel."""

    authentication_classes = [TenantJWTAuthentication]
    permission_classes = [IsAuthenticated, TenantRolePermission]
    read_roles = ALL_TENANT_ROLES
    write_roles = OPERATIONAL

    @extend_schema(
        summary="Comandos recientes del nodo",
        operation_id="node_commands_list",
        responses={200: dict},
        tags=["Nodos"],
    )
    def get(self, request, node_id):
        node = _tenant_node(node_id)
        if node is None:
            return Response({"detail": "No encontrado."}, status=404)
        commands = EdgeCommand.objects.filter(node=node).order_by("-created_at")[:50]
        return Response([command_body(command) for command in commands])

    @extend_schema(
        summary="Despachar comando al nodo",
        operation_id="node_command_dispatch",
        request=DispatchCommandSerializer,
        responses={200: dict},
        tags=["Nodos"],
    )
    def post(self, request, node_id):
        node = _tenant_node(node_id)
        if node is None:
            return Response({"detail": "No encontrado."}, status=404)
        incoming = DispatchCommandSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        data = incoming.validated_data
        payload = dict(data.get("payload") or {})
        if data["type"] == EdgeCommand.Type.OPEN_DOOR and not payload.get("actor"):
            payload["actor"] = request.user.get_username()
        try:
            command = dispatch_command(node, data["type"], payload, timeout=data.get("wait") or 0)
        except CommandValidationError as exc:
            return Response({"detail": exc.detail}, status=400)
        return Response(command_body(command))


class NodeCommandDetailView(APIView):
    authentication_classes = [TenantJWTAuthentication]
    permission_classes = [IsAuthenticated, TenantRolePermission]
    read_roles = ALL_TENANT_ROLES

    @extend_schema(
        summary="Estado de un comando",
        operation_id="node_command_retrieve",
        responses={200: dict},
        tags=["Nodos"],
    )
    def get(self, request, node_id, command_id):
        node = _tenant_node(node_id)
        if node is None:
            return Response({"detail": "No encontrado."}, status=404)
        command = EdgeCommand.objects.filter(node=node, pk=command_id).first()
        if command is None:
            return Response({"detail": "No encontrado."}, status=404)
        return Response(command_body(command))


def _tenant_node(node_id):
    return AccessNode.objects.filter(pk=node_id).first()


def _delta_params(request):
    raw_since = request.query_params.get("since_version", "0")
    raw_limit = request.query_params.get("limit", str(settings.EDGE_DELTA_DEFAULT_LIMIT))
    try:
        since = int(raw_since)
        limit = int(raw_limit)
    except ValueError:
        return (
            None,
            None,
            Response(
                {"detail": "since_version y limit deben ser enteros."},
                status=400,
            ),
        )
    if since < 0 or limit < 1:
        return (
            None,
            None,
            Response(
                {"detail": "since_version no puede ser negativo y limit debe ser mayor que cero."},
                status=400,
            ),
        )
    return since, limit, None


def _optional_uuid(raw, field):
    if raw in (None, ""):
        return None, None
    try:
        return uuid.UUID(str(raw)), None
    except ValueError:
        return None, Response({"detail": f"{field} debe ser un UUID."}, status=400)


def _wait_param(request):
    raw = request.query_params.get("wait", "0")
    try:
        wait = float(raw)
    except ValueError:
        return None, Response({"detail": "wait debe ser un número."}, status=400)
    if wait < 0:
        return None, Response({"detail": "wait no puede ser negativo."}, status=400)
    return wait, None
