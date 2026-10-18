from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.tenants.context import set_current_organization
from apps.tenants.models import Membership, Organization


class TenantJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        authenticated = super().authenticate(request)
        if authenticated is None:
            return None
        user, token = authenticated
        request.organization = None
        request.membership = None
        org_id = token.payload.get("org_id")
        if not org_id:
            set_current_organization(None)
            return user, token
        organization = Organization.objects.filter(pk=org_id, is_active=True).first()
        if organization is None:
            raise AuthenticationFailed(
                "La organización del token no existe o está inactiva.",
                code="invalid_organization",
            )
        membership = Membership.objects.filter(user=user, organization=organization).first()
        if membership is None and not user.is_superadmin:
            raise AuthenticationFailed(
                "El usuario no pertenece a la organización del token.",
                code="invalid_membership",
            )
        set_current_organization(organization)
        request.organization = organization
        request.membership = membership
        return user, token
