from celery import shared_task

from orders.services import (
    cancel_expired_pending_orders,
    mark_due_physical_orders_signed,
    auto_complete_eligible_physical_order,
    auto_complete_eligible_virtual_order,
)


@shared_task
def cancel_expired_pending_orders_task():
    return cancel_expired_pending_orders()


@shared_task
def mark_due_physical_orders_signed_task():
    return mark_due_physical_orders_signed()


@shared_task
def auto_complete_eligible_orders_task():
    count = 0
    count += auto_complete_eligible_physical_order()
    count += auto_complete_eligible_virtual_order()

    return count
