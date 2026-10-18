from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.tenants.models import Membership, Organization


def resolve_role(user: User, organization: Organization | None) -> str | None:
    if organization is None:
        return None
    if user.is_superadmin:
        return "SUPERADMIN"
    membership = Membership.objects.filter(user=user, organization=organization).first()
    if membership is None:
        raise AuthenticationFailed("Sin membresía en la organización.", code="no_membership")
    return membership.role


def default_organization(user: User) -> Organization | None:
    memberships = list(
        Membership.objects.filter(user=user, organization__is_active=True).select_related(
            "organization"
        )
    )
    if len(memberships) == 1:
        return memberships[0].organization
    if len(memberships) == 0 and not user.is_superadmin:
        raise AuthenticationFailed(
            "El usuario no tiene una organización activa.",
            code="no_organization",
        )
    return None


def issue_tokens(user: User, organization: Organization | None) -> dict:
    role = resolve_role(user, organization)
    refresh = RefreshToken.for_user(user)
    org_id = str(organization.id) if organization else None
    refresh["org_id"] = org_id
    refresh["role"] = role
    refresh["is_superadmin"] = bool(user.is_superadmin)
    access = refresh.access_token
    return {
        "refresh": str(refresh),
        "access": str(access),
        "organization_id": org_id,
        "role": role,
        "is_superadmin": user.is_superadmin,
    }
