import django_filters

from apps.kiosk.models import FaceEnrollmentSession, Kiosk


class KioskFilter(django_filters.FilterSet):
    door = django_filters.UUIDFilter(field_name="door_id")

    class Meta:
        model = Kiosk
        fields = ["door", "is_active"]


class FaceEnrollmentSessionFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter(field_name="employee_id")

    class Meta:
        model = FaceEnrollmentSession
        fields = ["employee", "status", "started_by"]
