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
            "kiosk_token",
            "deleted_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "last_seen_at",
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
    class Meta:
        model = FaceEnrollmentSession
        fields = [
            "id",
            "organization",
            "employee",
            "started_by",
            "started_by_user",
            "started_by_kiosk",
            "status",
            "faceauth_user_id",
            "created_at",
            "expires_at",
        ]
        read_only_fields = fields
