import django_filters

from apps.access.models import AccessAnomaly, AccessLog, Door, Reader


class DoorFilter(django_filters.FilterSet):
    node = django_filters.UUIDFilter(field_name="node_id")
    zone = django_filters.UUIDFilter(field_name="zone_id")

    class Meta:
        model = Door
        fields = ["node", "zone", "direction", "apb_mode", "face_enabled", "is_active"]


class ReaderFilter(django_filters.FilterSet):
    door = django_filters.UUIDFilter(field_name="door_id")
    reader_profile = django_filters.UUIDFilter(field_name="reader_profile_id")

    class Meta:
        model = Reader
        fields = ["door", "reader_profile", "is_active", "reader_device_id"]


class AccessAnomalyFilter(django_filters.FilterSet):
    node = django_filters.UUIDFilter(field_name="node_id")
    employee = django_filters.UUIDFilter(field_name="employee_id")

    class Meta:
        model = AccessAnomaly
        fields = ["node", "employee", "kind"]


class AccessLogFilter(django_filters.FilterSet):
    node = django_filters.UUIDFilter(field_name="node_id")
    door = django_filters.UUIDFilter(field_name="door_id")
    employee = django_filters.UUIDFilter(field_name="employee_id")
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
