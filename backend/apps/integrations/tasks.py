import logging

from celery import shared_task

from apps.integrations.webhooks import deliver_once

logger = logging.getLogger(__name__)


@shared_task(name="apps.integrations.tasks.deliver_webhook")
def deliver_webhook(delivery_id: str) -> str:
    try:
        return deliver_once(delivery_id)
    except Exception:
        logger.exception("Fallo inesperado entregando webhook %s", delivery_id)
        return "error"
