import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.tokens import issue_tokens
from apps.tenants.models import Membership, Organization

PASSWORD = "Nube-Segura-2026!"


@pytest.fixture
def password():
    return PASSWORD


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", timezone="America/Bogota")


@pytest.fixture
def globex(db):
    return Organization.objects.create(name="Globex", slug="globex", timezone="America/Mexico_City")


def make_user(username: str, email: str, **extra) -> User:
    return User.objects.create_user(
        username=username,
        email=email,
        password=PASSWORD,
        first_name="Ada",
        last_name="Admin",
        **extra,
    )


def auth_client(user: User, organization: Organization | None) -> APIClient:
    tokens = issue_tokens(user, organization)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client


@pytest.fixture
def acme_admin(acme):
    user = make_user("acme.admin", "admin@acme.test")
    Membership.objects.create(user=user, organization=acme, role=Membership.Role.ADMIN)
    return user


@pytest.fixture
def acme_operator(acme):
    user = make_user("acme.operator", "operator@acme.test")
    Membership.objects.create(user=user, organization=acme, role=Membership.Role.OPERATOR)
    return user


@pytest.fixture
def acme_viewer(acme):
    user = make_user("acme.viewer", "viewer@acme.test")
    Membership.objects.create(user=user, organization=acme, role=Membership.Role.VIEWER)
    return user


@pytest.fixture
def globex_admin(globex):
    user = make_user("globex.admin", "admin@globex.test")
    Membership.objects.create(user=user, organization=globex, role=Membership.Role.ADMIN)
    return user


@pytest.fixture
def superadmin(db):
    return make_user(
        "superadmin",
        "superadmin@example.com",
        is_superadmin=True,
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def acme_client(acme_admin, acme):
    return auth_client(acme_admin, acme)


@pytest.fixture
def operator_client(acme_operator, acme):
    return auth_client(acme_operator, acme)


@pytest.fixture
def viewer_client(acme_viewer, acme):
    return auth_client(acme_viewer, acme)


@pytest.fixture
def globex_client(globex_admin, globex):
    return auth_client(globex_admin, globex)


@pytest.fixture
def super_client(superadmin):
    return auth_client(superadmin, None)
