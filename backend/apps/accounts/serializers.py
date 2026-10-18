from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.accounts.tokens import default_organization, issue_tokens
from apps.tenants.models import Membership, Organization


class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data.update(issue_tokens(self.user, default_organization(self.user)))
        return data


class TenantTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        refresh = RefreshToken(attrs["refresh"])
        user = User.objects.filter(pk=refresh["user_id"], is_active=True).first()
        if user is None:
            raise AuthenticationFailed("Usuario inactivo.", code="inactive_user")
        org_id = refresh.payload.get("org_id")
        if org_id:
            organization = Organization.objects.filter(pk=org_id, is_active=True).first()
            if organization is None:
                raise AuthenticationFailed(
                    "La organización del token no está activa.",
                    code="invalid_organization",
                )
            if (
                not user.is_superadmin
                and not Membership.objects.filter(
                    user=user,
                    organization=organization,
                ).exists()
            ):
                raise AuthenticationFailed(
                    "La membresía ya no es válida.",
                    code="invalid_membership",
                )
        return data


class SwitchOrganizationSerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()

    def validate_organization_id(self, value):
        organization = Organization.objects.filter(pk=value, is_active=True).first()
        if organization is None:
            raise serializers.ValidationError("La organización no existe o está inactiva.")
        user = self.context["request"].user
        if (
            not user.is_superadmin
            and not Membership.objects.filter(
                user=user,
                organization=organization,
            ).exists()
        ):
            raise serializers.ValidationError("No pertenece a esa organización.")
        return organization
