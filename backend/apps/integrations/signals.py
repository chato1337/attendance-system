import uuid

from django.db.models.signals import post_save

from apps.integrations.models import FaceAuthPendingDeletion
from apps.people.models import Credential, Employee


def connect() -> None:
    post_save.connect(
        queue_credential_deletion,
        sender=Credential,
        dispatch_uid="faceauth.credential.deletion",
    )
    post_save.connect(
        queue_employee_deletion,
        sender=Employee,
        dispatch_uid="faceauth.employee.deletion",
    )


def queue_face_deletion(organization_id, user_id, reason: str) -> None:
    try:
        parsed = uuid.UUID(str(user_id))
    except (TypeError, ValueError):
        return
    pending = FaceAuthPendingDeletion.all_objects.filter(
        organization_id=organization_id,
        faceauth_user_id=parsed,
        processed_at__isnull=True,
    ).exists()
    if pending:
        return
    FaceAuthPendingDeletion.all_objects.create(
        organization_id=organization_id,
        faceauth_user_id=parsed,
        reason=reason[:64],
    )


def queue_credential_deletion(sender, instance: Credential, **kwargs) -> None:
    if instance.type != Credential.CredentialType.FACIAL:
        return
    if instance.is_active and not instance.deleted_at:
        return
    queue_face_deletion(instance.organization_id, instance.payload, "credential_revoked")


def queue_employee_deletion(sender, instance: Employee, **kwargs) -> None:
    if instance.is_active and not instance.deleted_at:
        return
    credentials = Credential.all_objects.filter(
        employee=instance,
        type=Credential.CredentialType.FACIAL,
    )
    for credential in credentials:
        queue_face_deletion(instance.organization_id, credential.payload, "employee_inactive")
