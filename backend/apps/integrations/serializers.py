import secrets

from rest_framework import serializers

from apps.common.secrets import hash_secret
from apps.integrations.authentication import TOKEN_PREFIX, APITokenPrincipal
from apps.integrations.faceauth.flow import cors_origins, hosted_redirect_uris
from apps.integrations.models import (
    API_TOKEN_SCOPES,
    WEBHOOK_EVENTS,
    APIToken,
    FaceAuthIntegration,
    WebhookDelivery,
    WebhookSubscription,
    normalize_events,
    normalize_scopes,
)


class FaceAuthIntegrationSerializer(serializers.ModelSerializer):
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=False)
    api_key_set = serializers.SerializerMethodField()
    cors_origins = serializers.SerializerMethodField()
    hosted_redirect_uris = serializers.SerializerMethodField()

    class Meta:
        model = FaceAuthIntegration
        fields = [
            "id",
            "organization",
            "app_id",
            "api_key",
            "api_key_set",
            "api_url",
            "server_api_url",
            "web_url",
            "cors_origins",
            "hosted_redirect_uris",
            "enabled",
            "allow_panel_login",
            "allow_kiosk_self_enrollment",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "api_key_set",
            "cors_origins",
            "hosted_redirect_uris",
            "created_at",
            "updated_at",
        ]

    def get_api_key_set(self, obj) -> bool:
        return bool(obj.api_key)

    def get_cors_origins(self, obj) -> list[str]:
        return cors_origins()

    def get_hosted_redirect_uris(self, obj) -> list[str]:
        return hosted_redirect_uris()

    def validate(self, attrs):
        enabled = attrs.get("enabled", getattr(self.instance, "enabled", False))
        app_id = attrs.get("app_id", getattr(self.instance, "app_id", ""))
        has_key = "api_key" in attrs or bool(getattr(self.instance, "api_key", ""))
        if enabled and (not app_id or not has_key):
            raise serializers.ValidationError("Para habilitar Face-Auth indique app_id y api_key.")
        return attrs

    def create(self, validated_data):
        return FaceAuthIntegration.objects.create(**validated_data)


class WebhookSubscriptionSerializer(serializers.ModelSerializer):
    secret = serializers.CharField(write_only=True, required=False, allow_blank=False)
    secret_value = serializers.CharField(read_only=True, required=False)

    class Meta:
        model = WebhookSubscription
        fields = [
            "id",
            "organization",
            "name",
            "url",
            "secret",
            "secret_value",
            "events",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "organization", "secret_value", "created_at", "updated_at"]

    def validate_events(self, value):
        events = normalize_events(value)
        if not events:
            raise serializers.ValidationError(
                f"Eventos válidos: {', '.join(sorted(WEBHOOK_EVENTS))}."
            )
        return events

    def validate_url(self, value):
        if not value.startswith(("http://", "https://")):
            raise serializers.ValidationError("La URL debe ser http(s).")
        return value

    def create(self, validated_data):
        plain = validated_data.pop("secret", None) or secrets.token_urlsafe(32)
        subscription = WebhookSubscription.objects.create(secret=plain, **validated_data)
        subscription.secret_value = plain
        return subscription

    def update(self, instance, validated_data):
        plain = validated_data.pop("secret", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if plain:
            instance.secret = plain
            instance.secret_value = plain
        instance.save()
        return instance


class WebhookDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookDelivery
        fields = [
            "id",
            "subscription",
            "event",
            "payload",
            "attempt",
            "status",
            "response_status",
            "response_body",
            "next_retry_at",
            "created_at",
            "completed_at",
        ]
        read_only_fields = fields


class WebhookTestSerializer(serializers.Serializer):
    event = serializers.ChoiceField(
        choices=[(code, code) for code in sorted(WEBHOOK_EVENTS)],
        default="access.granted",
    )


class APITokenSerializer(serializers.ModelSerializer):
    token = serializers.CharField(read_only=True, required=False)

    class Meta:
        model = APIToken
        fields = [
            "id",
            "organization",
            "name",
            "token",
            "token_prefix",
            "scopes",
            "is_active",
            "last_used_at",
            "expires_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "token",
            "token_prefix",
            "last_used_at",
            "created_at",
        ]

    def validate_scopes(self, value):
        scopes = normalize_scopes(value)
        if not scopes:
            raise serializers.ValidationError(
                f"Alcances válidos: {', '.join(sorted(API_TOKEN_SCOPES))}."
            )
        return scopes

    def create(self, validated_data):
        plain = f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
        request = self.context.get("request")
        user = getattr(request, "user", None)
        created_by = None
        if (
            user is not None
            and not isinstance(user, APITokenPrincipal)
            and getattr(user, "pk", None)
        ):
            created_by = user
        token = APIToken.objects.create(
            token_hash=hash_secret(plain),
            token_prefix=plain[:12],
            created_by=created_by,
            **validated_data,
        )
        token.token = plain
        return token


class EmployeeBulkSerializer(serializers.Serializer):
    employees = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
        max_length=2000,
    )
