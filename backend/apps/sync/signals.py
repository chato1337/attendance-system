from django.dispatch import Signal

# Fases 5, 6 y 8 se suscriben. El receptor debe ser rápido o diferir con on_commit.
access_log_created = Signal()
device_status_changed = Signal()
