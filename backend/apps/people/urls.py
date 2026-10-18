from rest_framework.routers import DefaultRouter

from apps.people.views import CredentialViewSet, DepartmentViewSet, EmployeeViewSet

router = DefaultRouter()
router.register("departments", DepartmentViewSet, basename="department")
router.register("employees", EmployeeViewSet, basename="employee")
router.register("credentials", CredentialViewSet, basename="credential")

urlpatterns = router.urls
