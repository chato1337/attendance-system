from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integrations"
    verbose_name = "Integraciones"

    def ready(self):
        from apps.integrations.signals import connect

        connect()
