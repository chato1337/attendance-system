from rest_framework.permissions import BasePermission

from apps.tenants.models import Membership

ALL_TENANT_ROLES = {
    Membership.Role.ADMIN,
    Membership.Role.OPERATOR,
    Membership.Role.VIEWER,
}
WRITE_ROLES = {Membership.Role.ADMIN, Membership.Role.OPERATOR}


class IsSuperAdmin(BasePermission):
    message = "Solo un superadministrador puede realizar esta operación."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_superadmin)


class TenantRolePermission(BasePermission):
    message = "No tiene permiso para esta operación en la organización activa."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        organization = getattr(request, "organization", None)
        if organization is None:
            self.message = "Seleccione una organización activa."
            return False
        if user.is_superadmin:
            return True
        membership = getattr(request, "membership", None)
        if membership is None or membership.organization_id != organization.id:
            self.message = "El usuario no pertenece a la organización activa."
            return False
        action = getattr(view, "action", None)
        action_roles = getattr(view, "action_roles", {})
        if action in action_roles:
            allowed = action_roles[action]
        elif request.method in ("GET", "HEAD", "OPTIONS"):
            allowed = getattr(view, "read_roles", ALL_TENANT_ROLES)
        else:
            allowed = getattr(view, "write_roles", WRITE_ROLES)
        if membership.role not in allowed:
            self.message = "Su rol no permite esta operación."
            return False
        return True
