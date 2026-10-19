from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny

from apps.common.views import HealthView

admin.site.site_header = "Control de acceso"
admin.site.site_title = "Control de acceso"
admin.site.index_title = "Administración"

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "api/schema/",
        SpectacularAPIView.as_view(permission_classes=[AllowAny]),
        name="schema",
    ),
    path(
        "api/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema", permission_classes=[AllowAny]),
        name="swagger-ui",
    ),
    path("api/v1/health/", HealthView.as_view(), name="health"),
    path("api/v1/", include("apps.sync.urls")),
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.tenants.urls")),
    path("api/v1/", include("apps.people.urls")),
    path("api/v1/", include("apps.access.urls")),
    path("api/v1/", include("apps.kiosk.urls")),
    path("api/v1/", include("apps.integrations.urls")),
    path("api/v1/", include("apps.reports.urls")),
]
