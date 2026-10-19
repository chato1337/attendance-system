import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import TimeStampedModel
from apps.integrations.fields import EncryptedTextField
from apps.tenants.models import TenantModel

WEBHOOK_EVENT_CHOICES = [
    ("access.granted", "Acceso concedido"),
    ("access.denied", "Acceso denegado"),
    ("device.status_changed", "Estado del nodo"),
    ("employee.updated", "Empleado actualizado"),
    ("occupancy.threshold", "Umbral de aforo"),
    ("face.enrolled", "Rostro enrolado"),
]

WEBHOOK_EVENTS = {code for code, _label in WEBHOOK_EVENT_CHOICES}

API_TOKEN_SCOPES = {
    "employees:read",
    "employees:write",
    "webhooks:manage",
}


class FaceAuthIntegration(TenantModel, TimeStampedModel):
    app_id = models.CharField(max_length=64, blank=True)
    api_key = EncryptedTextField(blank=True)
    api_url = models.URLField()
    server_api_url = models.URLField(
        blank=True,
        help_text="URL que usa la nube si el navegador no puede alcanzar la misma dirección.",
    )
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


class FaceAuthPendingDeletion(TenantModel):
    """Baja de un perfil biométrico pendiente del endpoint FA-4."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    faceauth_user_id = models.UUIDField()
    reason = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "baja facial pendiente"
        verbose_name_plural = "bajas faciales pendientes"
        ordering = ["-created_at"]
        base_manager_name = "all_objects"
        default_manager_name = "objects"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "faceauth_user_id"],
                condition=models.Q(processed_at__isnull=True),
                name="uniq_pending_face_deletion",
            )
        ]


class WebhookSubscription(TenantModel, TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    url = models.URLField()
    secret = EncryptedTextField()
    events = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "suscripción webhook"
        verbose_name_plural = "suscripciones webhook"
        ordering = ["name"]
        base_manager_name = "all_objects"
        default_manager_name = "objects"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="uniq_webhook_name_per_org",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        events = normalize_events(self.events)
        if not events:
            raise ValidationError("Indique al menos un evento válido.")
        self.events = events


class WebhookDeliveryStatus(models.TextChoices):
    PENDING = "PENDING", "Pendiente"
    SUCCESS = "SUCCESS", "Entregado"
    FAILED = "FAILED", "Fallido"
    EXHAUSTED = "EXHAUSTED", "Agotado"


class WebhookDelivery(TenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(
        WebhookSubscription,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    event = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    attempt = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(
        max_length=12,
        choices=WebhookDeliveryStatus.choices,
        default=WebhookDeliveryStatus.PENDING,
    )
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "entrega webhook"
        verbose_name_plural = "entregas webhook"
        ordering = ["-created_at"]
        base_manager_name = "all_objects"
        default_manager_name = "objects"
        indexes = [
            models.Index(
                fields=["organization", "status", "next_retry_at"],
                name="webhook_delivery_retry_idx",
            ),
            models.Index(
                fields=["organization", "subscription", "created_at"],
                name="webhook_delivery_sub_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.event} {self.status}"


class APIToken(TenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    token_hash = models.CharField(max_length=64, unique=True)
    token_prefix = models.CharField(max_length=16)
    scopes = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="api_tokens",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "token de API"
        verbose_name_plural = "tokens de API"
        ordering = ["-created_at"]
        base_manager_name = "all_objects"
        default_manager_name = "objects"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="uniq_api_token_name_per_org",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        scopes = normalize_scopes(self.scopes)
        if not scopes:
            raise ValidationError("Indique al menos un alcance válido.")
        self.scopes = scopes


def normalize_events(value) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: list[str] = []
    for item in value:
        if not isinstance(item, str) or item not in WEBHOOK_EVENTS or item in seen:
            continue
        seen.append(item)
    return seen


def normalize_scopes(value) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: list[str] = []
    for item in value:
        if not isinstance(item, str) or item not in API_TOKEN_SCOPES or item in seen:
            continue
        seen.append(item)
    return seen
