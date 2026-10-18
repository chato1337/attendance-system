import uuid

from django.core.exceptions import ValidationError
from django.db import models

from apps.access.normalization import validate_steps
from apps.common.models import Activatable
from apps.people.models import Credential
from apps.tenants.models import TenantModel, TenantSyncableModel, validate_timezone


class Direction(models.TextChoices):
    IN = "IN", "Ingreso"
    OUT = "OUT", "Salida"


class ApbMode(models.TextChoices):
    OFF = "OFF", "Apagado"
    SOFT = "SOFT", "Blando"
    HARD = "HARD", "Duro"


class Zone(TenantSyncableModel):
    name = models.CharField(max_length=120)

    class Meta(TenantSyncableModel.Meta):
        abstract = False
        verbose_name = "zona"
        verbose_name_plural = "zonas"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="uniq_zone_name_per_org")
        ]

    def __str__(self) -> str:
        return self.name


class ReaderProfile(TenantSyncableModel):
    name = models.CharField(max_length=150)
    credential_type = models.CharField(max_length=20, choices=Credential.CredentialType.choices)
    normalization = models.JSONField(default=list, blank=True)
    min_length = models.PositiveIntegerField(default=1)
    max_length = models.PositiveIntegerField(default=128)

    class Meta(TenantSyncableModel.Meta):
        abstract = False
        verbose_name = "perfil de lector"
        verbose_name_plural = "perfiles de lector"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="uniq_reader_profile_name_per_org",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        if self.min_length > self.max_length:
            raise ValidationError("min_length no puede ser mayor que max_length.")
        validate_steps(self.normalization)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class AccessNode(TenantModel, Activatable):
    name = models.CharField(max_length=150)
    site = models.CharField(max_length=150, blank=True)
    timezone = models.CharField(max_length=64, default="UTC", validators=[validate_timezone])
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    is_online = models.BooleanField(default=False)
    api_key_hash = models.CharField(max_length=64, unique=True)
    gateway_version_reported = models.CharField(max_length=40, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_sync_version = models.BigIntegerField(default=0)

    class Meta:
        verbose_name = "nodo"
        verbose_name_plural = "nodos"
        ordering = ["name"]
        base_manager_name = "all_objects"
        default_manager_name = "objects"
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="uniq_node_name_per_org")
        ]

    def __str__(self) -> str:
        return self.name


class Door(TenantSyncableModel):
    node = models.ForeignKey(AccessNode, on_delete=models.PROTECT, related_name="doors")
    zone = models.ForeignKey(
        Zone,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="doors",
    )
    name = models.CharField(max_length=150)
    relay_device_id = models.CharField(max_length=64)
    direction = models.CharField(max_length=3, choices=Direction.choices)
    apb_mode = models.CharField(max_length=8, choices=ApbMode.choices, default=ApbMode.OFF)
    required_factors = models.JSONField(default=list, blank=True)
    face_enabled = models.BooleanField(default=False)

    class Meta(TenantSyncableModel.Meta):
        abstract = False
        verbose_name = "puerta"
        verbose_name_plural = "puertas"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["node", "name"], name="uniq_door_name_per_node")
        ]

    def __str__(self) -> str:
        return self.name


class Reader(TenantSyncableModel):
    door = models.ForeignKey(Door, on_delete=models.CASCADE, related_name="readers")
    reader_profile = models.ForeignKey(
        ReaderProfile,
        on_delete=models.PROTECT,
        related_name="readers",
    )
    name = models.CharField(max_length=150)
    reader_device_id = models.CharField(max_length=64)

    class Meta(TenantSyncableModel.Meta):
        abstract = False
        verbose_name = "lector"
        verbose_name_plural = "lectores"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class AccessStatus(models.TextChoices):
    GRANTED = "GRANTED", "Concedido"
    DENIED = "DENIED", "Denegado"


class AccessMethod(models.TextChoices):
    RFID = "RFID", "RFID"
    FINGERPRINT = "FINGERPRINT", "Huella"
    FACIAL = "FACIAL", "Rostro"
    PIN = "PIN", "PIN"
    REMOTE = "REMOTE", "Apertura remota"


class AccessSource(models.TextChoices):
    GATEWAY = "gateway", "Gateway"
    CLOUD = "cloud", "Nube"
    REMOTE = "remote", "Remoto"


class DenialReason(models.TextChoices):
    UNKNOWN_CREDENTIAL = "UNKNOWN_CREDENTIAL", "Credencial desconocida"
    INACTIVE = "INACTIVE", "Inactiva"
    EXPIRED = "EXPIRED", "Vencida"
    APB_VIOLATION = "APB_VIOLATION", "Anti-passback"
    UNKNOWN_DEVICE = "UNKNOWN_DEVICE", "Dispositivo desconocido"
    MALFORMED_READ = "MALFORMED_READ", "Lectura mal formada"
    FACE_NOT_ALLOWED = "FACE_NOT_ALLOWED", "Rostro no habilitado en la puerta"
    NODE_OFFLINE = "NODE_OFFLINE", "Nodo sin conexión"


class AccessLog(TenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    node = models.ForeignKey(AccessNode, on_delete=models.PROTECT, related_name="logs")
    door = models.ForeignKey(
        Door,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
    )
    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_logs",
    )
    credential = models.ForeignKey(
        Credential,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_logs",
    )
    timestamp = models.DateTimeField(db_index=True)
    direction = models.CharField(max_length=3, choices=Direction.choices)
    status = models.CharField(max_length=10, choices=AccessStatus.choices)
    denial_reason = models.CharField(
        max_length=64,
        choices=DenialReason.choices,
        blank=True,
    )
    method = models.CharField(max_length=20, choices=AccessMethod.choices, blank=True)
    source = models.CharField(max_length=20, choices=AccessSource.choices, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "marcación"
        verbose_name_plural = "marcaciones"
        ordering = ["-timestamp"]
        base_manager_name = "all_objects"
        default_manager_name = "objects"
        indexes = [
            models.Index(fields=["employee", "timestamp"], name="accesslog_employee_ts_idx"),
            models.Index(fields=["node", "timestamp"], name="accesslog_node_ts_idx"),
        ]
