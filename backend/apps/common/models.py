import uuid

from django.db import connection, models


class TimeStampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True


class Activatable(TimeStampedModel):
    is_active = models.BooleanField(default=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


class SyncableModel(Activatable):
    """Fila sincronizable hacia el Edge.

    `version` la asigna el trigger PostgreSQL `assign_sync_version` en cada
    INSERT/UPDATE, desde la secuencia global `sync_version_seq`. `save()`
    relee ese valor para que la instancia quede actualizada.
    """

    version = models.BigIntegerField(default=0, db_index=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if connection.vendor == "postgresql":
            self.refresh_from_db(fields=["version"])
