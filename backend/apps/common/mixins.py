from django.utils import timezone

from apps.tenants.context import get_current_organization


class TenantWriteMixin:
    def perform_create(self, serializer):
        serializer.save(organization=get_current_organization())

    def perform_destroy(self, instance):
        instance.is_active = False
        if hasattr(instance, "deleted_at"):
            instance.deleted_at = timezone.now()
        instance.save()


class ReactivationMixin:
    def update(self, instance, validated_data):
        if validated_data.get("is_active") is True and hasattr(instance, "deleted_at"):
            instance.deleted_at = None
        return super().update(instance, validated_data)
