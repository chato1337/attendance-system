import uuid

from django.db.models.signals import post_save

from apps.integrations.models import FaceAuthPendingDeletion
from apps.integrations.webhooks import enqueue_access_log, enqueue_device_status
from apps.people.models import Credential, Employee
from apps.sync.signals import access_log_created, device_status_changed


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
    access_log_created.connect(on_access_log, dispatch_uid="webhooks.access_log")
    device_status_changed.connect(on_device_status, dispatch_uid="webhooks.device_status")


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


def on_access_log(sender, log, **kwargs) -> None:
    enqueue_access_log(log)


def on_device_status(sender, node, is_online, **kwargs) -> None:
    enqueue_device_status(node, is_online)
