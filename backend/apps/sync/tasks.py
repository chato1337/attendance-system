from celery import shared_task

from apps.sync.commands import expire_due_commands
from apps.sync.heartbeat import mark_stale_nodes_offline


@shared_task
def mark_stale_nodes_offline_task() -> int:
    return mark_stale_nodes_offline()


@shared_task
def expire_edge_commands() -> int:
    return expire_due_commands()
