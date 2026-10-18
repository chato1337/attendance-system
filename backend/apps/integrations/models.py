import uuid

from django.db import models

from apps.common.models import TimeStampedModel
from apps.integrations.fields import EncryptedTextField
from apps.tenants.models import TenantModel


class FaceAuthIntegration(TenantModel, TimeStampedModel):
    app_id = models.CharField(max_length=64, blank=True)
    api_key = EncryptedTextField(blank=True)
    api_url = models.URLField()
    web_url = models.URLField(blank=True)
    enabled = models.BooleanField(default=False)
    allow_panel_login = models.BooleanField(default=False)
    allow_kiosk_self_enrollment = models.BooleanField(default=False)

    class Meta:
        verbose_name = "integración Face-Auth"
        verbose_name_plural = "integraciones Face-Auth"
        base_manager_name = "all_objects"
        default_manager_name = "objects"
        constraints = [
            models.UniqueConstraint(fields=["organization"], name="uniq_faceauth_per_org")
        ]

    def __str__(self) -> str:
        return f"Face-Auth {self.organization}"


class PendingFaceIdentity(TenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    faceauth_user_id = models.UUIDField()
    email = models.EmailField(blank=True)
    claims = models.JSONField(default=dict, blank=True)
    resolved_employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pending_face_identities",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "identidad facial pendiente"
        verbose_name_plural = "identidades faciales pendientes"
        ordering = ["-created_at"]
        base_manager_name = "all_objects"
        default_manager_name = "objects"
