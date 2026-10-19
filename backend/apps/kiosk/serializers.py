from rest_framework import serializers

from apps.common.mixins import ReactivationMixin
from apps.common.secrets import generate_secret
from apps.kiosk.models import FaceEnrollmentSession, Kiosk


class KioskSerializer(ReactivationMixin, serializers.ModelSerializer):
    kiosk_token = serializers.SerializerMethodField()

    class Meta:
        model = Kiosk
        fields = [
            "id",
            "organization",
            "door",
            "name",
            "is_active",
            "last_seen_at",
            "camera_permission",
            "kiosk_token",
            "deleted_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "last_seen_at",
            "camera_permission",
            "kiosk_token",
            "deleted_at",
            "created_at",
            "updated_at",
        ]

    def get_kiosk_token(self, obj) -> str | None:
        return getattr(obj, "plaintext_kiosk_token", None)

    def create(self, validated_data):
        plain, digest = generate_secret()
        kiosk = Kiosk.objects.create(kiosk_token_hash=digest, **validated_data)
        kiosk.plaintext_kiosk_token = plain
        return kiosk


class FaceEnrollmentSessionSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = FaceEnrollmentSession
        fields = [
            "id",
            "organization",
            "employee",
            "employee_name",
            "started_by",
            "started_by_user",
            "started_by_kiosk",
            "status",
            "faceauth_user_id",
            "failure_code",
            "detail",
            "created_at",
            "expires_at",
        ]
        read_only_fields = fields

    def get_employee_name(self, obj) -> str:
        employee = obj.employee
        return f"{employee.first_name} {employee.last_name}".strip()


class RedirectTokenSerializer(serializers.Serializer):
    redirect_token = serializers.CharField(max_length=8192)


class EnrollmentFailSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=64)
    message = serializers.CharField(max_length=500, required=False, allow_blank=True)


class KioskHeartbeatSerializer(serializers.Serializer):
    camera_permission = serializers.ChoiceField(choices=["unknown", "granted", "denied", "prompt"])


class KioskLookupSerializer(serializers.Serializer):
    document_id = serializers.CharField(max_length=64)


class KioskMeSerializer(serializers.Serializer):
    kiosk_id = serializers.UUIDField()
    name = serializers.CharField()
    door_id = serializers.UUIDField()
    door_name = serializers.CharField()
    direction = serializers.CharField()
    organization_name = serializers.CharField()
    organization_slug = serializers.CharField()
    face_enabled = serializers.BooleanField()
    faceauth_enabled = serializers.BooleanField()
    app_id = serializers.CharField()
    api_url = serializers.CharField()
    web_url = serializers.CharField()
    allow_kiosk_self_enrollment = serializers.BooleanField()
    camera_permission = serializers.CharField()


class FaceIdentifyResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    code = serializers.CharField()
    message = serializers.CharField()
    door_id = serializers.UUIDField()
    kiosk_id = serializers.UUIDField()
    log_id = serializers.UUIDField(allow_null=True)
    created_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)
