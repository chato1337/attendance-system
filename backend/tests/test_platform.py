from django.core.management import call_command
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.integrations.models import FaceAuthIntegration
from apps.people.models import Employee
from apps.tenants.models import Membership
from conftest import PASSWORD, auth_client


def test_health_does_not_require_authentication(db):
    response = APIClient().get("/api/v1/health/")
    assert response.status_code == 200
    assert response.data["status"] == "ok"


def test_login_refresh_and_organization_switch(acme, globex, acme_admin):
    Membership.objects.create(user=acme_admin, organization=globex, role=Membership.Role.VIEWER)
    client = APIClient()
    login = client.post(
        "/api/v1/auth/token/",
        {"username": "acme.admin", "password": PASSWORD},
        format="json",
    )
    assert login.status_code == 200
    assert login.data["organization_id"] is None
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    assert client.get("/api/v1/employees/").status_code == 403
    switched = client.post(
        "/api/v1/auth/switch-organization/",
        {"organization_id": str(acme.id)},
        format="json",
    )
    assert switched.status_code == 200
    assert switched.data["organization_id"] == str(acme.id)
    assert switched.data["role"] == Membership.Role.ADMIN
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {switched.data['access']}")
    me = client.get("/api/v1/auth/me/")
    assert me.status_code == 200
    assert me.data["organization_id"] == acme.id
    assert len(me.data["memberships"]) == 2
    Membership.objects.filter(user=acme_admin, organization=acme).delete()
    refresh = APIClient().post(
        "/api/v1/auth/token/refresh/",
        {"refresh": switched.data["refresh"]},
        format="json",
    )
    assert refresh.status_code == 401


def test_single_membership_is_selected_on_login(acme, acme_admin):
    response = APIClient().post(
        "/api/v1/auth/token/",
        {"username": "acme.admin", "password": PASSWORD},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["organization_id"] == str(acme.id)
    assert response.data["role"] == "ADMIN"


def test_user_without_organization_cannot_login(db):
    User.objects.create_user(username="solo", email="solo@example.com", password=PASSWORD)
    response = APIClient().post(
        "/api/v1/auth/token/",
        {"username": "solo", "password": PASSWORD},
        format="json",
    )
    assert response.status_code == 401


def test_token_for_another_organization_is_rejected(acme_admin, globex):
    refresh = RefreshToken.for_user(acme_admin)
    refresh["org_id"] = str(globex.id)
    refresh["role"] = "ADMIN"
    refresh["is_superadmin"] = False
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    assert client.get("/api/v1/employees/").status_code == 401


def test_superadmin_provisions_an_organization(super_client, superadmin):
    assert super_client.get("/api/v1/employees/").status_code == 403
    created = super_client.post(
        "/api/v1/organizations/",
        {
            "name": "Nueva",
            "slug": "nueva",
            "timezone": "America/Bogota",
            "initial_admin": {
                "username": "nueva.admin",
                "email": "admin@nueva.test",
                "password": PASSWORD,
            },
        },
        format="json",
    )
    assert created.status_code == 201
    switched = auth_client(superadmin, None)
    token = switched.post(
        "/api/v1/auth/switch-organization/",
        {"organization_id": created.data["id"]},
        format="json",
    )
    switched.credentials(HTTP_AUTHORIZATION=f"Bearer {token.data['access']}")
    profiles = switched.get("/api/v1/reader-profiles/")
    assert profiles.status_code == 200
    assert profiles.data["count"] == 3
    login = APIClient().post(
        "/api/v1/auth/token/",
        {"username": "nueva.admin", "password": PASSWORD},
        format="json",
    )
    assert login.status_code == 200
    assert login.data["organization_id"] == created.data["id"]


def test_non_admin_cannot_manage_organizations_or_memberships(acme_client, operator_client):
    assert acme_client.get("/api/v1/organizations/").status_code == 403
    created = operator_client.post(
        "/api/v1/memberships/",
        {"username": "otro", "email": "otro@acme.test", "password": PASSWORD, "role": "VIEWER"},
        format="json",
    )
    assert created.status_code == 403


def test_admin_creates_membership_and_faceauth_key_is_write_only(
    acme_client, operator_client, acme
):
    created = acme_client.post(
        "/api/v1/memberships/",
        {
            "username": "nuevo.viewer",
            "email": "nuevo@acme.test",
            "password": PASSWORD,
            "role": "VIEWER",
        },
        format="json",
    )
    assert created.status_code == 201
    assert created.data["user_username"] == "nuevo.viewer"
    assert operator_client.get("/api/v1/faceauth-integration/").status_code == 403
    updated = acme_client.patch(
        "/api/v1/faceauth-integration/",
        {"app_id": "app-acme", "api_key": "secreto-faceauth", "enabled": True},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["api_key_set"] is True
    assert "secreto-faceauth" not in str(updated.data)
    stored = FaceAuthIntegration.all_objects.get(organization=acme)
    assert stored.api_key == "secreto-faceauth"
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT api_key FROM integrations_faceauthintegration WHERE id = %s",
            [stored.id],
        )
        raw = cursor.fetchone()[0]
    assert raw != "secreto-faceauth"


def test_kiosk_token_is_shown_only_once(acme_client, acme):
    from apps.access.models import AccessNode, Door

    node = AccessNode.all_objects.create(
        organization=acme,
        name="Sede",
        timezone="UTC",
        api_key_hash="b" * 64,
    )
    door = Door.all_objects.create(
        organization=acme,
        node=node,
        name="Portería",
        relay_device_id="COM4",
        direction="IN",
    )
    created = acme_client.post(
        "/api/v1/kiosks/",
        {"door": str(door.id), "name": "Kiosco 1"},
        format="json",
    )
    assert created.status_code == 201
    assert created.data["kiosk_token"]
    fetched = acme_client.get(f"/api/v1/kiosks/{created.data['id']}/")
    assert fetched.data["kiosk_token"] is None
    rotated = acme_client.post(f"/api/v1/kiosks/{created.data['id']}/regenerate-token/")
    assert rotated.data["kiosk_token"] not in (None, created.data["kiosk_token"])


def test_openapi_schema_lists_the_admin_api(db):
    response = APIClient().get("/api/schema/")
    assert response.status_code == 200
    body = response.content.decode()
    for path in (
        "/api/v1/employees/",
        "/api/v1/employees/face-readiness/",
        "/api/v1/reader-profiles/",
        "/api/v1/nodes/",
        "/api/v1/kiosks/",
        "/api/v1/faceauth-integration/",
        "/api/v1/access-logs/",
        "/api/v1/auth/switch-organization/",
    ):
        assert path in body


def test_seed_demo_creates_two_isolated_organizations(db):
    call_command("seed_demo")
    assert set(User.objects.values_list("username", flat=True)) >= {
        "superadmin",
        "acme.admin",
        "globex.admin",
        "multi.admin",
    }
    login = APIClient().post(
        "/api/v1/auth/token/",
        {"username": "acme.admin", "password": PASSWORD},
        format="json",
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    documents = {row["document_id"] for row in client.get("/api/v1/employees/").data["results"]}
    assert "1001" in documents
    assert "2001" not in documents
    readiness = client.get("/api/v1/employees/face-readiness/")
    issues = {row["document_id"]: row["issues"] for row in readiness.data["results"]}
    assert "missing_email" in issues["1002"]
    assert "duplicate_email" in issues["1003"]


def test_admin_lists_every_organization(client, superadmin, acme):
    employee = Employee.all_objects.create(
        organization=acme,
        document_id="1",
        first_name="Visible",
        last_name="Admin",
    )
    client.force_login(superadmin)
    pages = [
        "/admin/",
        "/admin/accounts/user/",
        "/admin/tenants/organization/",
        "/admin/tenants/membership/",
        "/admin/people/department/",
        "/admin/people/employee/",
        "/admin/people/credential/",
        "/admin/access/zone/",
        "/admin/access/readerprofile/",
        "/admin/access/accessnode/",
        "/admin/access/door/",
        "/admin/access/reader/",
        "/admin/access/accesslog/",
        "/admin/kiosk/kiosk/",
        "/admin/kiosk/faceenrollmentsession/",
        "/admin/integrations/faceauthintegration/",
        "/admin/integrations/pendingfaceidentity/",
    ]
    for url in pages:
        response = client.get(url)
        assert response.status_code == 200, url
    detail = client.get(f"/admin/people/employee/{employee.id}/change/")
    assert detail.status_code == 200
    assert b"Visible" in detail.content
