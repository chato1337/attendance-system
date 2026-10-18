import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField("email", unique=True)
    is_superadmin = models.BooleanField(
        default=False,
        help_text="Rol de plataforma. Puede administrar organizaciones sin pertenecer a ellas.",
    )
    faceauth_user_id = models.UUIDField(
        null=True,
        blank=True,
        unique=True,
        help_text="user_id de Face-Auth para el login opcional del panel.",
    )

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self) -> str:
        return self.username
