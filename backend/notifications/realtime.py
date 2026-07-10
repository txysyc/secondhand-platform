"""站内通知 WebSocket 推送工具。"""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def user_notification_group_name(user_id):
    """返回指定用户的通知频道组名称。"""

    return f"notifications_user_{user_id}"


def push_notification_created(user_id, notification_data, unread_count):
    """向在线用户推送新通知事件。"""

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    try:
        async_to_sync(channel_layer.group_send)(
            user_notification_group_name(user_id),
            {
                "type": "notification.created",
                "notification": notification_data,
                "unread_count": unread_count,
            },
        )
    except Exception:
        # 实时推送失败不能影响主业务通知持久化。
        logger.exception("站内通知 WebSocket 推送失败")


def push_notification_unread_count(user_id, unread_count):
    """向在线用户推送最新未读通知数量。"""

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    try:
        async_to_sync(channel_layer.group_send)(
            user_notification_group_name(user_id),
            {
                "type": "notification.unread_count",
                "unread_count": unread_count,
            },
        )
    except Exception:
        # 实时计数同步失败不影响通知已读状态持久化。
        logger.exception("通知未读数 WebSocket 推送失败")
