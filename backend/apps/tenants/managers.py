from django.db import models

from apps.tenants.context import get_current_organization


class TenantManager(models.Manager):
    """Filtra por la organización del contexto. Sin tenant, no devuelve filas."""

    def get_queryset(self):
        queryset = super().get_queryset()
        organization = get_current_organization()
        if organization is None:
            return queryset.none()
        return queryset.filter(organization=organization)
