from celery import shared_task

from apps.access.occupancy import reconcile_occupancy


@shared_task
def reconcile_occupancy_task() -> int:
    return reconcile_occupancy()
