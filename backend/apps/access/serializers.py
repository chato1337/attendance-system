from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.access.models import AccessLog, AccessNode, Door, Reader, ReaderProfile, Zone
from apps.access.normalization import validate_steps
from apps.common.mixins import ReactivationMixin
from apps.common.secrets import generate_secret
from apps.tenants.models import validate_timezone

SYNC_READ_ONLY = [
    "id",
    "organization",
    "deleted_at",
    "version",
    "created_at",
    "updated_at",
]


class ZoneSerializer(ReactivationMixin, serializers.ModelSerializer):
    class Meta:
        model = Zone
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
        read_only_fields = SYNC_READ_ONLY


class ReaderProfileSerializer(ReactivationMixin, serializers.ModelSerializer):
    class Meta:
        model = ReaderProfile
        fields = [
            "id",
            "organization",
            "name",
            "credential_type",
            "normalization",
            "min_length",
            "max_length",
            "is_active",
            "deleted_at",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = SYNC_READ_ONLY

    def validate_normalization(self, value):
        try:
            validate_steps(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def validate(self, attrs):
        min_length = attrs.get("min_length", getattr(self.instance, "min_length", 1))
        max_length = attrs.get("max_length", getattr(self.instance, "max_length", 128))
        if min_length > max_length:
            raise serializers.ValidationError(
                {"min_length": "min_length no puede ser mayor que max_length."}
            )
        return attrs


class ReaderProfilePreviewSerializer(serializers.Serializer):
    sample = serializers.CharField(allow_blank=True)
    normalization = serializers.JSONField(required=False)
    min_length = serializers.IntegerField(required=False, min_value=0)
    max_length = serializers.IntegerField(required=False, min_value=1)


class AccessNodeSerializer(ReactivationMixin, serializers.ModelSerializer):
    api_key = serializers.SerializerMethodField()

    class Meta:
        model = AccessNode
        fields = [
            "id",
            "organization",
            "name",
            "site",
            "timezone",
            "is_active",
            "is_online",
            "last_heartbeat_at",
            "last_sync_at",
            "last_sync_version",
            "gateway_version_reported",
            "agent_version",
            "gateway_connected",
            "listening_devices",
            "queue_size",
            "commands_connected",
            "api_key",
            "deleted_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "is_online",
            "last_heartbeat_at",
            "last_sync_at",
            "last_sync_version",
            "gateway_version_reported",
            "agent_version",
            "gateway_connected",
            "listening_devices",
            "queue_size",
            "commands_connected",
            "api_key",
            "deleted_at",
            "created_at",
            "updated_at",
        ]

    def get_api_key(self, obj) -> str | None:
        return getattr(obj, "plaintext_api_key", None)

    def validate_timezone(self, value):
        try:
            validate_timezone(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def create(self, validated_data):
        plain, digest = generate_secret()
        node = AccessNode.objects.create(api_key_hash=digest, **validated_data)
        node.plaintext_api_key = plain
        return node


class DoorSerializer(ReactivationMixin, serializers.ModelSerializer):
    class Meta:
        model = Door
        fields = [
            "id",
            "organization",
            "node",
            "zone",
            "name",
            "relay_device_id",
            "direction",
            "apb_mode",
            "required_factors",
            "face_enabled",
            "is_active",
            "deleted_at",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = SYNC_READ_ONLY

    def validate_required_factors(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("required_factors debe ser una lista.")
        return value


class ReaderSerializer(ReactivationMixin, serializers.ModelSerializer):
    class Meta:
        model = Reader
        fields = [
            "id",
            "organization",
            "door",
            "reader_profile",
            "name",
            "reader_device_id",
            "is_active",
            "deleted_at",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = SYNC_READ_ONLY

    def validate(self, attrs):
        door = attrs.get("door", getattr(self.instance, "door", None))
        device_id = attrs.get("reader_device_id", getattr(self.instance, "reader_device_id", None))
        profile = attrs.get("reader_profile", getattr(self.instance, "reader_profile", None))
        if door is not None and device_id:
            conflict = Reader.objects.filter(door__node_id=door.node_id, reader_device_id=device_id)
            if self.instance is not None:
                conflict = conflict.exclude(pk=self.instance.pk)
            if conflict.exists():
                raise serializers.ValidationError(
                    {"reader_device_id": "Ese device_id ya está usado por otro lector del nodo."}
                )
        same_organization = (
            door is not None
            and profile is not None
            and door.organization_id != profile.organization_id
        )
        if same_organization:
            raise serializers.ValidationError(
                {"reader_profile": "El perfil no pertenece a la organización de la puerta."}
            )
        return attrs


class AccessLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccessLog
        fields = [
            "id",
            "organization",
            "node",
            "door",
            "employee",
            "credential",
            "timestamp",
            "direction",
            "status",
            "denial_reason",
            "method",
            "source",
            "created_at",
        ]
        read_only_fields = fields
