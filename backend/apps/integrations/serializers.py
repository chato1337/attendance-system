from rest_framework import serializers

from apps.integrations.models import FaceAuthIntegration


class FaceAuthIntegrationSerializer(serializers.ModelSerializer):
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=False)
    api_key_set = serializers.SerializerMethodField()

    class Meta:
        model = FaceAuthIntegration
        fields = [
            "id",
            "organization",
            "app_id",
            "api_key",
            "api_key_set",
            "api_url",
            "web_url",
            "enabled",
            "allow_panel_login",
            "allow_kiosk_self_enrollment",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "organization", "api_key_set", "created_at", "updated_at"]

    def get_api_key_set(self, obj) -> bool:
        return bool(obj.api_key)

    def validate(self, attrs):
        enabled = attrs.get("enabled", getattr(self.instance, "enabled", False))
        app_id = attrs.get("app_id", getattr(self.instance, "app_id", ""))
        has_key = "api_key" in attrs or bool(getattr(self.instance, "api_key", ""))
        if enabled and (not app_id or not has_key):
            raise serializers.ValidationError("Para habilitar Face-Auth indique app_id y api_key.")
        return attrs

    def create(self, validated_data):
        return FaceAuthIntegration.objects.create(**validated_data)
