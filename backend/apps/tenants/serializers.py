from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from apps.accounts.services import create_or_attach_membership
from apps.tenants.models import Membership, Organization, validate_timezone


class InitialAdminSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(required=False, allow_blank=True, default="")
    last_name = serializers.CharField(required=False, allow_blank=True, default="")


class OrganizationSerializer(serializers.ModelSerializer):
    initial_admin = InitialAdminSerializer(write_only=True, required=False)

    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "slug",
            "timezone",
            "is_active",
            "settings",
            "initial_admin",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_settings(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("settings debe ser un objeto JSON.")
        return value

    def validate_timezone(self, value):
        try:
            validate_timezone(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def create(self, validated_data):
        initial_admin = validated_data.pop("initial_admin", None)
        with transaction.atomic():
            organization = super().create(validated_data)
            if initial_admin:
                create_or_attach_membership(
                    organization=organization,
                    role=Membership.Role.ADMIN,
                    **initial_admin,
                )
        return organization


class MembershipSerializer(serializers.ModelSerializer):
    username = serializers.CharField(write_only=True, required=False)
    email = serializers.EmailField(write_only=True, required=False)
    password = serializers.CharField(write_only=True, required=False)
    first_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    last_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    user_id = serializers.UUIDField(source="user.id", read_only=True)
    user_username = serializers.CharField(source="user.username", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Membership
        fields = [
            "id",
            "user_id",
            "user_username",
            "user_email",
            "username",
            "email",
            "password",
            "first_name",
            "last_name",
            "role",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def create(self, validated_data):
        organization = validated_data.pop("organization")
        username = validated_data.pop("username", None)
        if not username:
            raise serializers.ValidationError({"username": "Indique el usuario."})
        return create_or_attach_membership(
            organization=organization,
            username=username,
            role=validated_data["role"],
            email=validated_data.pop("email", None),
            password=validated_data.pop("password", None),
            first_name=validated_data.pop("first_name", ""),
            last_name=validated_data.pop("last_name", ""),
        )

    def update(self, instance, validated_data):
        for key in ("username", "email", "password", "first_name", "last_name", "organization"):
            validated_data.pop(key, None)
        return super().update(instance, validated_data)
