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
    door = models.ForeignKey("access.Door", on_delete=models.PROTECT, related_name="kiosks")
    name = models.CharField(max_length=150)
    kiosk_token_hash = models.CharField(max_length=64, unique=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

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
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=enrollment_expiry)

    class Meta:
        verbose_name = "sesión de enrolamiento facial"
        verbose_name_plural = "sesiones de enrolamiento facial"
        ordering = ["-created_at"]
        base_manager_name = "all_objects"
        default_manager_name = "objects"
