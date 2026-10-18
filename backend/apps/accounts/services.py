from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.tenants.models import Membership, Organization


def create_or_attach_membership(
    *,
    organization: Organization,
    username: str,
    role: str,
    email: str | None = None,
    password: str | None = None,
    first_name: str = "",
    last_name: str = "",
) -> Membership:
    user = User.objects.filter(username=username).first()
    if user is None:
        if not email:
            raise ValidationError({"email": "El email es obligatorio para un usuario nuevo."})
        if not password:
            raise ValidationError(
                {"password": "La contraseña es obligatoria para un usuario nuevo."}
            )
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError({"email": "Ya existe un usuario con ese email."})
        candidate = User(username=username, email=email, first_name=first_name, last_name=last_name)
        try:
            validate_password(password, user=candidate)
        except DjangoValidationError as exc:
            raise ValidationError({"password": list(exc.messages)}) from exc
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )
    elif Membership.objects.filter(user=user, organization=organization).exists():
        raise ValidationError({"username": "El usuario ya pertenece a la organización."})
    return Membership.objects.create(user=user, organization=organization, role=role)
