import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import Activatable
from apps.tenants.models import TenantModel


def enrollment_expiry():
    return timezone.now() + timedelta(minutes=15)


class Kiosk(TenantModel, Activatable):
    class CameraPermission(models.TextChoices):
        UNKNOWN = "unknown", "Desconocido"
        GRANTED = "granted", "Concedido"
        DENIED = "denied", "Denegado"
        PROMPT = "prompt", "Pendiente"

    door = models.ForeignKey("access.Door", on_delete=models.PROTECT, related_name="kiosks")
    name = models.CharField(max_length=150)
    kiosk_token_hash = models.CharField(max_length=64, unique=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    camera_permission = models.CharField(
        max_length=16,
        choices=CameraPermission.choices,
        default=CameraPermission.UNKNOWN,
    )

    class Meta:
        verbose_name = "kiosco"
        verbose_name_plural = "kioscos"
        ordering = ["name"]
        base_manager_name = "all_objects"
        default_manager_name = "objects"
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="uniq_kiosk_name_per_org")
        ]

    def __str__(self) -> str:
        return self.name


class FaceEnrollmentSession(TenantModel):
    class StartedBy(models.TextChoices):
        USER = "USER", "Usuario del panel"
        KIOSK = "KIOSK", "Kiosco"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        COMPLETED = "COMPLETED", "Completada"
        FAILED = "FAILED", "Fallida"
        EXPIRED = "EXPIRED", "Expirada"
        REJECTED = "REJECTED", "Rechazada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.CASCADE,
        related_name="face_enrollment_sessions",
    )
    started_by = models.CharField(max_length=8, choices=StartedBy.choices)
    started_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="face_enrollment_sessions",
    )
    started_by_kiosk = models.ForeignKey(
        Kiosk,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="face_enrollment_sessions",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    faceauth_user_id = models.UUIDField(null=True, blank=True)
    failure_code = models.CharField(max_length=64, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=enrollment_expiry)

    class Meta:
        verbose_name = "sesión de enrolamiento facial"
        verbose_name_plural = "sesiones de enrolamiento facial"
        ordering = ["-created_at"]
        base_manager_name = "all_objects"
        default_manager_name = "objects"


class FaceIdentificationRequest(TenantModel):
    """Resultado persistido de un redirect_token. El kiosco consulta por id."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        REJECTED = "REJECTED", "Rechazada"
        UNKNOWN_FACE = "UNKNOWN_FACE", "Rostro desconocido"
        GRANTED = "GRANTED", "Concedida"
        DENIED = "DENIED", "Denegada"
        NODE_UNREACHABLE = "NODE_UNREACHABLE", "Nodo inaccesible"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kiosk = models.ForeignKey(Kiosk, on_delete=models.PROTECT, related_name="face_requests")
    door = models.ForeignKey("access.Door", on_delete=models.PROTECT, related_name="face_requests")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    token_digest = models.CharField(max_length=64, unique=True)
    token_jti = models.CharField(max_length=64, blank=True)
    faceauth_user_id = models.UUIDField(null=True, blank=True)
    email = models.EmailField(blank=True)
    code = models.CharField(max_length=64, blank=True)
    message = models.TextField(blank=True)
    access_log = models.ForeignKey(
        "access.AccessLog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="face_requests",
    )
    edge_log_id = models.UUIDField(null=True, blank=True)
    command = models.ForeignKey(
        "sync.EdgeCommand",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="face_requests",
    )
    timings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "solicitud de identificación facial"
        verbose_name_plural = "solicitudes de identificación facial"
        ordering = ["-created_at"]
        base_manager_name = "all_objects"
        default_manager_name = "objects"
        indexes = [
            models.Index(
                fields=["organization", "created_at"],
                name="face_request_org_created_idx",
            ),
        ]
