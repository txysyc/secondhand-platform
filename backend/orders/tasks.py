from celery import shared_task

from orders.services import (
    cancel_expired_pending_orders,
    mark_due_physical_orders_signed,
    auto_complete_eligible_physical_order,
    auto_complete_eligible_virtual_order,
)


@shared_task
def cancel_expired_pending_orders_task():
    """Celery 任务：取消已超过支付期限的待支付订单。"""

    return cancel_expired_pending_orders()


@shared_task
def mark_due_physical_orders_signed_task():
    """Celery 任务：把到达模拟签收时间的实体订单标记为已签收。"""

    return mark_due_physical_orders_signed()


@shared_task
def auto_complete_eligible_orders_task():
    """Celery 任务：自动完成满足等待期的实体和虚拟订单。"""

    count = 0
    count += auto_complete_eligible_physical_order()
    count += auto_complete_eligible_virtual_order()

    return count
