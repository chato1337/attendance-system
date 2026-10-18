import django_filters

from apps.access.models import AccessLog, Door, Reader


class DoorFilter(django_filters.FilterSet):
    class Meta:
        model = Door
        fields = ["node", "zone", "direction", "apb_mode", "face_enabled", "is_active"]


class ReaderFilter(django_filters.FilterSet):
    class Meta:
        model = Reader
        fields = ["door", "reader_profile", "is_active", "reader_device_id"]


class AccessLogFilter(django_filters.FilterSet):
    timestamp_after = django_filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr="gte")
    timestamp_before = django_filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr="lte")

    class Meta:
        model = AccessLog
        fields = [
            "node",
            "door",
            "employee",
            "status",
            "direction",
            "method",
            "source",
            "denial_reason",
        ]
