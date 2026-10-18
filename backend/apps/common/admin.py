from django.contrib import admin


class UnscopedAdmin(admin.ModelAdmin):
    """El admin operativo ve todas las organizaciones y filtra en la UI."""

    def get_queryset(self, request):
        manager = getattr(self.model, "all_objects", None)
        if manager is None:
            return super().get_queryset(request)
        return manager.all()
