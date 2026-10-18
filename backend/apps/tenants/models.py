import uuid
from zoneinfo import available_timezones

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import SyncableModel
from apps.tenants.managers import TenantManager


def validate_timezone(value: str) -> None:
    if value not in available_timezones():
        raise ValidationError("Zona horaria inválida.")


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=80, unique=True)
    timezone = models.CharField(max_length=64, default="UTC", validators=[validate_timezone])
    is_active = models.BooleanField(default=True)
    settings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "organización"
        verbose_name_plural = "organizaciones"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class TenantModel(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True
        base_manager_name = "all_objects"
        default_manager_name = "objects"


class TenantSyncableModel(TenantModel, SyncableModel):
    class Meta:
        abstract = True
        base_manager_name = "all_objects"
        default_manager_name = "objects"


class Membership(models.Model):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrador"
        OPERATOR = "OPERATOR", "Operador"
        VIEWER = "VIEWER", "Consulta"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "membresía"
        verbose_name_plural = "membresías"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "organization"],
                name="uniq_membership_user_org",
            )
        ]
        ordering = ["organization__name", "user__username"]

    def __str__(self) -> str:
        return f"{self.user} @ {self.organization} ({self.role})"
