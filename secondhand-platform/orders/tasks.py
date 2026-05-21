from celery import shared_task

from orders.services import cancel_expired_pending_orders


@shared_task
def cancel_expired_pending_orders_task():
    return cancel_expired_pending_orders()
