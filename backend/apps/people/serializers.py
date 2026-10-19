import uuid

from rest_framework import serializers

from apps.common.mixins import ReactivationMixin
from apps.people.models import Credential, Department, Employee


class DepartmentSerializer(ReactivationMixin, serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = [
            "id",
            "organization",
            "name",
            "is_active",
            "deleted_at",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "deleted_at",
            "version",
            "created_at",
            "updated_at",
        ]


class EmployeeSerializer(ReactivationMixin, serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = [
            "id",
            "organization",
            "department",
            "document_id",
            "first_name",
            "last_name",
            "email",
            "is_active",
            "is_inside",
            "last_presence_at",
            "presence_node",
            "presence_zone",
            "presence_reset_at",
            "deleted_at",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "is_inside",
            "last_presence_at",
            "presence_node",
            "presence_zone",
            "presence_reset_at",
            "deleted_at",
            "version",
            "created_at",
            "updated_at",
        ]


class CredentialSerializer(ReactivationMixin, serializers.ModelSerializer):
    class Meta:
        model = Credential
        fields = [
            "id",
            "organization",
            "employee",
            "type",
            "payload",
            "source",
            "reader_profile",
            "is_active",
            "valid_from",
            "valid_until",
            "deleted_at",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "deleted_at",
            "version",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        credential_type = attrs.get("type", getattr(self.instance, "type", None))
        payload = attrs.get("payload", getattr(self.instance, "payload", None))
        if credential_type == Credential.CredentialType.FACIAL and payload is not None:
            try:
                attrs["payload"] = str(uuid.UUID(str(payload)))
            except ValueError as exc:
                raise serializers.ValidationError(
                    {"payload": "Para FACIAL el payload debe ser el UUID de Face-Auth."}
                ) from exc
        valid_from = attrs.get("valid_from", getattr(self.instance, "valid_from", None))
        valid_until = attrs.get("valid_until", getattr(self.instance, "valid_until", None))
        if valid_from and valid_until and valid_until < valid_from:
            raise serializers.ValidationError(
                {"valid_until": "La vigencia final no puede ser anterior al inicio."}
            )
        profile = attrs.get("reader_profile", getattr(self.instance, "reader_profile", None))
        if profile is not None and credential_type and profile.credential_type != credential_type:
            raise serializers.ValidationError(
                {"reader_profile": "El perfil no corresponde al tipo de credencial."}
            )
        return attrs


class FaceReadinessSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    document_id = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField(allow_null=True)
    issues = serializers.ListField(child=serializers.CharField())
