from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.access.profiles import create_default_reader_profiles
from apps.tenants.context import reset_current_organization, set_current_organization
from apps.tenants.models import Organization


@receiver(post_save, sender=Organization)
def ensure_default_reader_profiles(sender, instance, created, **kwargs):
    if not created:
        return
    token = set_current_organization(instance)
    try:
        create_default_reader_profiles(instance)
    finally:
        reset_current_organization(token)
