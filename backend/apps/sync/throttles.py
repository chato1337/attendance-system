from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle


class EdgeNodeThrottle(SimpleRateThrottle):
    """Límite por nodo autenticado. No aplica a peticiones anónimas."""

    scope = "edge_node"

    def get_rate(self):
        # Lee la tasa en cada petición para que los tests puedan cambiarla.
        return api_settings.DEFAULT_THROTTLE_RATES[self.scope]

    def get_cache_key(self, request, view):
        node = getattr(request, "node", None)
        if node is None:
            principal = getattr(request, "user", None)
            node = getattr(principal, "node", None)
        if node is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": node.pk}
