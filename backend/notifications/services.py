"""站内通知业务服务。"""

import logging

from django.db import transaction
from django.utils import timezone

from notifications.models import Notification
from notifications.realtime import (
    push_notification_created,
    push_notification_unread_count,
)
from notifications.selectors import get_unread_notification_count
from notifications.serializers import NotificationSerializer

logger = logging.getLogger(__name__)


def create_notification_after_commit(**kwargs):
    """在当前事务提交后创建通知并推送实时事件。"""

    transaction.on_commit(lambda: create_notification(**kwargs))


def create_notification(
    *,
    recipient,
    actor=None,
    type,
    title,
    content,
    target_type,
    target_id,
    target_url,
    payload=None,
):
    """创建站内通知，并向在线接收者推送实时事件。"""

    if recipient is None or not getattr(recipient, "is_active", False):
        return None
    if actor is not None and getattr(actor, "pk", None) == recipient.pk:
        return None

    try:
        notification = Notification.objects.create(
            recipient=recipient,
            actor=actor,
            type=type,
            title=title,
            content=content,
            target_type=target_type,
            target_id=target_id,
            target_url=target_url,
            payload=payload or {},
        )
        push_notification_created(
            recipient.pk,
            NotificationSerializer(notification).data,
            get_unread_notification_count(recipient),
        )
        return notification
    except Exception:
        # 通知是旁路能力，失败时只记录日志，不能影响评论和订单主流程。
        logger.exception("站内通知创建失败")
        return None


def mark_notification_read(user, notification):
    """把当前用户的一条通知标记为已读，重复调用保持成功。"""

    if notification.recipient_id != user.pk:
        return None
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
        push_notification_unread_count(
            user.pk,
            get_unread_notification_count(user),
        )
    return notification


def mark_all_notifications_read(user):
    """把当前用户全部未读通知标记为已读。"""

    updated_count = Notification.objects.filter(
        recipient=user,
        read_at__isnull=True,
    ).update(read_at=timezone.now())
    if updated_count:
        push_notification_unread_count(
            user.pk,
            get_unread_notification_count(user),
        )
    return updated_count
