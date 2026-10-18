from rest_framework.routers import DefaultRouter

from apps.tenants.views import MembershipViewSet, OrganizationViewSet

router = DefaultRouter()
router.register("organizations", OrganizationViewSet, basename="organization")
router.register("memberships", MembershipViewSet, basename="membership")

urlpatterns = router.urls
