from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.access.models import AccessNode, ApbMode, Direction, Door, Reader, ReaderProfile, Zone
from apps.access.profiles import create_default_reader_profiles
from apps.accounts.models import User
from apps.common.secrets import generate_secret
from apps.kiosk.models import Kiosk
from apps.people.models import Credential, Department, Employee
from apps.tenants.models import Membership, Organization

DEMO_PASSWORD = "Nube-Segura-2026!"


class Command(BaseCommand):
    help = "Carga dos organizaciones de demostración para probar el aislamiento."

    def handle(self, *args, **options):
        if not settings.DEBUG and not getattr(settings, "ALLOW_DEMO_SEED", False):
            raise CommandError("seed_demo solo puede ejecutarse con DEBUG=true.")
        with transaction.atomic():
            acme = self._organization("Acme", "acme", "America/Bogota")
            globex = self._organization("Globex", "globex", "America/Mexico_City")
            self._user(
                "superadmin",
                "superadmin@example.com",
                is_superadmin=True,
                is_staff=True,
                is_superuser=True,
            )
            self._member("acme.admin", "admin@acme.test", acme, Membership.Role.ADMIN)
            self._member("acme.operator", "operator@acme.test", acme, Membership.Role.OPERATOR)
            self._member("acme.viewer", "viewer@acme.test", acme, Membership.Role.VIEWER)
            self._member("globex.admin", "admin@globex.test", globex, Membership.Role.ADMIN)
            both = self._user("multi.admin", "multi@example.com")
            self._membership(both, acme, Membership.Role.ADMIN)
            self._membership(both, globex, Membership.Role.ADMIN)
            self._acme_people(acme)
            self._globex_people(globex)
        self.stdout.write(self.style.SUCCESS("Datos de demostración listos."))
        self.stdout.write(f"Contraseña de todos los usuarios demo: {DEMO_PASSWORD}")
        self.stdout.write("Usuarios: superadmin, acme.admin, acme.operator, acme.viewer,")
        self.stdout.write("          globex.admin, multi.admin (Acme y Globex).")

    def _organization(self, name, slug, timezone):
        organization, created = Organization.objects.get_or_create(
            slug=slug,
            defaults={"name": name, "timezone": timezone, "is_active": True},
        )
        if not created:
            organization.name = name
            organization.timezone = timezone
            organization.is_active = True
            organization.save(update_fields=["name", "timezone", "is_active", "updated_at"])
        create_default_reader_profiles(organization)
        self.stdout.write(f"Organización {organization.name} ({organization.slug})")
        return organization

    def _user(self, username, email, **extra):
        user, _created = User.objects.get_or_create(
            username=username,
            defaults={"email": email, **extra},
        )
        user.email = email
        user.is_active = True
        for key, value in extra.items():
            setattr(user, key, value)
        user.set_password(DEMO_PASSWORD)
        user.save()
        return user

    def _membership(self, user, organization, role):
        Membership.objects.update_or_create(
            user=user,
            organization=organization,
            defaults={"role": role},
        )

    def _member(self, username, email, organization, role):
        user = self._user(username, email)
        self._membership(user, organization, role)
        return user

    def _acme_people(self, organization):
        operations, _ = Department.all_objects.get_or_create(
            organization=organization,
            name="Operaciones",
        )
        ana = self._employee(
            organization,
            "1001",
            "Ana",
            "Ruiz",
            "ana@acme.test",
            operations,
        )
        self._employee(organization, "1002", "Luis", "Peña", None, operations)
        self._employee(organization, "1003", "Marta", "Díaz", "duplicado@acme.test", operations)
        self._employee(organization, "1004", "Nora", "Díaz", "duplicado@acme.test", operations)
        profile = ReaderProfile.all_objects.get(
            organization=organization,
            name="RFID hexadecimal 8 dígitos",
        )
        Credential.all_objects.get_or_create(
            organization=organization,
            type=Credential.CredentialType.RFID,
            payload="0000AB12",
            defaults={
                "employee": ana,
                "source": Credential.Source.MANUAL,
                "reader_profile": profile,
                "is_active": True,
            },
        )
        zone, _ = Zone.all_objects.get_or_create(organization=organization, name="Planta baja")
        node = self._node(organization, "Sede Norte", "Bogotá", "America/Bogota")
        door, _ = Door.all_objects.get_or_create(
            node=node,
            name="Portería",
            defaults={
                "organization": organization,
                "zone": zone,
                "relay_device_id": "COM4",
                "direction": Direction.IN,
                "apb_mode": ApbMode.HARD,
            },
        )
        Reader.all_objects.get_or_create(
            door=door,
            reader_device_id="COM3",
            defaults={
                "organization": organization,
                "name": "Lector RFID portería",
                "reader_profile": profile,
            },
        )
        self._kiosk(organization, door, "Kiosco portería")

    def _globex_people(self, organization):
        admin_dept, _ = Department.all_objects.get_or_create(
            organization=organization,
            name="Administración",
        )
        self._employee(organization, "2001", "Bruno", "Díaz", "bruno@globex.test", admin_dept)
        zone, _ = Zone.all_objects.get_or_create(organization=organization, name="Oficina")
        node = self._node(organization, "Sede Centro", "Ciudad de México", "America/Mexico_City")
        profile = ReaderProfile.all_objects.get(
            organization=organization,
            name="RFID decimal 10 dígitos",
        )
        door, _ = Door.all_objects.get_or_create(
            node=node,
            name="Recepción",
            defaults={
                "organization": organization,
                "zone": zone,
                "relay_device_id": "COM6",
                "direction": Direction.IN,
                "apb_mode": ApbMode.SOFT,
            },
        )
        Reader.all_objects.get_or_create(
            door=door,
            reader_device_id="COM5",
            defaults={
                "organization": organization,
                "name": "Lector recepción",
                "reader_profile": profile,
            },
        )

    def _employee(self, organization, document_id, first_name, last_name, email, department):
        employee, _created = Employee.all_objects.get_or_create(
            organization=organization,
            document_id=document_id,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "department": department,
            },
        )
        return employee

    def _node(self, organization, name, site, timezone):
        node = AccessNode.all_objects.filter(organization=organization, name=name).first()
        if node is not None:
            self.stdout.write(f"  nodo {name}: api_key existente, no se vuelve a mostrar")
            return node
        plain, digest = generate_secret()
        node = AccessNode.all_objects.create(
            organization=organization,
            name=name,
            site=site,
            timezone=timezone,
            api_key_hash=digest,
        )
        self.stdout.write(f"  nodo {name} api_key: {plain}")
        return node

    def _kiosk(self, organization, door, name):
        kiosk = Kiosk.all_objects.filter(organization=organization, name=name).first()
        if kiosk is not None:
            self.stdout.write(f"  kiosco {name}: token existente, no se vuelve a mostrar")
            return kiosk
        plain, digest = generate_secret()
        kiosk = Kiosk.all_objects.create(
            organization=organization,
            door=door,
            name=name,
            kiosk_token_hash=digest,
        )
        self.stdout.write(f"  kiosco {name} kiosk_token: {plain}")
        return kiosk
