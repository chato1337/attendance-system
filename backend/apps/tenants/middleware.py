from apps.tenants.context import reset_current_organization, set_current_organization


class TenantContextMiddleware:
    """Limpia el tenant al entrar y al salir de cada petición."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = set_current_organization(None)
        try:
            return self.get_response(request)
        finally:
            reset_current_organization(token)
