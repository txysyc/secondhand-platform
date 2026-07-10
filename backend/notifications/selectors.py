"""站内通知查询入口。"""

from rest_framework.exceptions import ValidationError

from notifications.models import Notification


VALID_NOTIFICATION_STATUS = {"all", "read", "unread"}


def get_user_notifications(user, status_value="all"):
    """按当前用户和已读状态返回通知 QuerySet。"""

    status_value = status_value or "all"
    if status_value not in VALID_NOTIFICATION_STATUS:
        raise ValidationError("通知状态筛选参数无效")

    queryset = Notification.objects.filter(recipient=user).select_related(
        "actor",
        "actor__profile",
    )
    if status_value == "read":
        queryset = queryset.filter(read_at__isnull=False)
    if status_value == "unread":
        queryset = queryset.filter(read_at__isnull=True)
    return queryset.order_by("-created_at", "-id")


def get_unread_notification_count(user):
    """统计当前用户未读通知数量。"""

    return Notification.objects.filter(recipient=user, read_at__isnull=True).count()
