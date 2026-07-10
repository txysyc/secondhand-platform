from django.conf import settings
from django.db import models


class Notification(models.Model):
    """站内通知模型，保存通知历史、未读状态和前端跳转快照。"""

    class NotificationType(models.TextChoices):
        """当前阶段支持的通知类型。"""

        LISTING_COMMENTED = "listing_commented", "商品收到评论"
        COMMENT_REPLIED = "comment_replied", "评论收到回复"
        ORDER_CREATED = "order_created", "买家创建订单"
        ORDER_PAID = "order_paid", "买家支付成功"
        ORDER_DELIVERED = "order_delivered", "卖家发货或交付"
        ORDER_COMPLETED = "order_completed", "订单完成"

    class TargetType(models.TextChoices):
        """通知跳转目标类型。"""

        LISTING = "listing", "商品"
        ORDER = "order", "订单"
        COMMENT = "comment", "评论"

    class Meta:
        verbose_name = "站内通知"
        verbose_name_plural = "站内通知"
        ordering = ["-created_at", "-id"]
        indexes = [
            # 通知列表默认按用户和创建时间倒序读取。
            models.Index(
                fields=["recipient", "-created_at"],
                name="notif_recipient_created_idx",
            ),
            # 未读列表和未读数量统计复用该索引。
            models.Index(
                fields=["recipient", "read_at", "-created_at"],
                name="notif_recipient_read_idx",
            ),
            # 后台按通知类型排查业务事件。
            models.Index(
                fields=["type", "-created_at"],
                name="notif_type_created_idx",
            ),
        ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="接收用户",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triggered_notifications",
        verbose_name="触发用户",
    )
    type = models.CharField(
        max_length=40,
        choices=NotificationType.choices,
        verbose_name="通知类型",
    )
    title = models.CharField(max_length=100, verbose_name="通知标题")
    content = models.CharField(max_length=300, verbose_name="通知内容")
    target_type = models.CharField(
        max_length=20,
        choices=TargetType.choices,
        verbose_name="目标类型",
    )
    target_id = models.PositiveBigIntegerField(verbose_name="目标 ID")
    target_url = models.CharField(max_length=200, verbose_name="跳转地址")
    payload = models.JSONField(default=dict, blank=True, verbose_name="扩展数据")
    read_at = models.DateTimeField(null=True, blank=True, verbose_name="已读时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    def __str__(self):
        """返回后台和调试输出中展示的通知摘要。"""

        return f"{self.recipient} - {self.title}"
