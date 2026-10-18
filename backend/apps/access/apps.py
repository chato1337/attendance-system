from django.apps import AppConfig


class AccessConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.access"
    verbose_name = "Acceso"

    def ready(self) -> None:
        from apps.access import signals  # noqa: F401
