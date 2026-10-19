from django.db import models

from apps.tenants.models import TenantSyncableModel


class Department(TenantSyncableModel):
    name = models.CharField(max_length=120)

    class Meta(TenantSyncableModel.Meta):
        abstract = False
        verbose_name = "departamento"
        verbose_name_plural = "departamentos"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="uniq_department_name_per_org",
            )
        ]

    def __str__(self) -> str:
        return self.name


class Employee(TenantSyncableModel):
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )
    document_id = models.CharField(max_length=50)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    is_inside = models.BooleanField(default=False)
    last_presence_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp del último acceso concedido que definió is_inside.",
    )
    presence_node = models.ForeignKey(
        "access.AccessNode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="present_employees",
    )
    presence_zone = models.ForeignKey(
        "access.Zone",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="present_employees",
    )
    presence_reset_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Las marcaciones anteriores a este instante no vuelven a definir la presencia.",
    )

    class Meta(TenantSyncableModel.Meta):
        abstract = False
        verbose_name = "empleado"
        verbose_name_plural = "empleados"
        ordering = ["last_name", "first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "document_id"],
                name="uniq_employee_document_per_org",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "email"], name="employee_org_email_idx"),
            models.Index(fields=["organization", "is_inside"], name="employee_org_inside_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        else:
            self.email = None
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "email" not in update_fields:
            kwargs["update_fields"] = [*update_fields, "email"]
        super().save(*args, **kwargs)


class Credential(TenantSyncableModel):
    class CredentialType(models.TextChoices):
        FACIAL = "FACIAL", "Rostro (Face-Auth)"
        FINGERPRINT = "FINGERPRINT", "Huella"
        RFID = "RFID", "Tarjeta RFID/NFC"
        PIN = "PIN", "Código PIN"

    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        ASSISTED_ENROLLMENT = "ASSISTED_ENROLLMENT", "Enrolamiento asistido"
        FACEAUTH = "FACEAUTH", "Face-Auth"

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="credentials",
    )
    type = models.CharField(max_length=20, choices=CredentialType.choices)
    payload = models.TextField(
        help_text="Valor ya normalizado. Para FACIAL es el user_id de Face-Auth."
    )
    source = models.CharField(max_length=32, choices=Source.choices, default=Source.MANUAL)
    reader_profile = models.ForeignKey(
        "access.ReaderProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credentials",
    )
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)

    class Meta(TenantSyncableModel.Meta):
        abstract = False
        verbose_name = "credencial"
        verbose_name_plural = "credenciales"
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "type", "payload"],
                condition=models.Q(is_active=True),
                name="uniq_active_credential_per_org",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(valid_until__isnull=True)
                    | models.Q(valid_from__isnull=True)
                    | models.Q(valid_until__gte=models.F("valid_from"))
                ),
                name="credential_valid_window",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.type}:{self.payload}"

    def save(self, *args, **kwargs):
        if isinstance(self.payload, str):
            self.payload = self.payload.strip()
        super().save(*args, **kwargs)
