import django_filters

from apps.people.models import Credential, Employee


class EmployeeFilter(django_filters.FilterSet):
    class Meta:
        model = Employee
        fields = ["is_active", "department", "document_id", "is_inside"]


class CredentialFilter(django_filters.FilterSet):
    class Meta:
        model = Credential
        fields = ["employee", "type", "is_active", "source"]
