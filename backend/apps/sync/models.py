import uuid

from django.db import models

from apps.tenants.models import TenantModel


class EdgeCommand(TenantModel):
    """Comando durable de la nube hacia un nodo.

    Se persiste antes de enviarse. Una vez `EXPIRED` no se reintenta.
    """

    class Type(models.TextChoices):
        IDENTIFICATION = "identification", "Identificación"
        OPEN_DOOR = "open_door", "Apertura remota"
        SYNC_NOW = "sync_now", "Sincronizar"
        ENROLLMENT_MODE = "enrollment_mode", "Enrolamiento"
        RELOAD = "reload", "Recarga"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        SENT = "SENT", "Enviado"
        ACKED = "ACKED", "Confirmado"
        FAILED = "FAILED", "Fallido"
        EXPIRED = "EXPIRED", "Expirado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    node = models.ForeignKey(
        "access.AccessNode",
        on_delete=models.CASCADE,
        related_name="commands",
    )
    type = models.CharField(max_length=32, choices=Type.choices)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    expires_at = models.DateTimeField()
    result = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    acked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "comando de nodo"
        verbose_name_plural = "comandos de nodo"
        ordering = ["created_at"]
        base_manager_name = "all_objects"
        default_manager_name = "objects"
        indexes = [
            models.Index(fields=["node", "status", "expires_at"], name="edgecommand_poll_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.type} {self.status}"


class EnrollmentRead(TenantModel):
    """Lectura cruda capturada por el agente durante el enrolamiento asistido."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    node = models.ForeignKey(
        "access.AccessNode",
        on_delete=models.CASCADE,
        related_name="enrollment_reads",
    )
    reader = models.ForeignKey(
        "access.Reader",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enrollment_reads",
    )
    command = models.ForeignKey(
        EdgeCommand,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enrollment_reads",
    )
    raw = models.TextField(blank=True)
    payload = models.TextField(blank=True)
    credential_type = models.CharField(max_length=20, blank=True)
    error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "lectura de enrolamiento"
        verbose_name_plural = "lecturas de enrolamiento"
        ordering = ["-created_at"]
        base_manager_name = "all_objects"
        default_manager_name = "objects"

    def __str__(self) -> str:
        return self.raw or self.payload or str(self.id)
