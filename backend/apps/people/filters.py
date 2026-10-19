import django_filters

from apps.people.models import Credential, Employee


class EmployeeFilter(django_filters.FilterSet):
    # UUIDFilter compara la columna. Un ModelChoiceFilter evaluaría Employee/Department
    # al importar el módulo, cuando todavía no hay tenant, y el queryset quedaría vacío.
    department = django_filters.UUIDFilter(field_name="department_id")

    class Meta:
        model = Employee
        fields = ["is_active", "department", "document_id", "is_inside"]


class CredentialFilter(django_filters.FilterSet):
    employee = django_filters.UUIDFilter(field_name="employee_id")
    reader_profile = django_filters.UUIDFilter(field_name="reader_profile_id")

    class Meta:
        model = Credential
        fields = ["employee", "reader_profile", "type", "is_active", "source"]
