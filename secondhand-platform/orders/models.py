from django.db import models

from django.conf import settings


class Order(models.Model):
    """订单模型，保存交易状态、快照信息和关键流程时间。"""

    class Meta:
        verbose_name = "订单"
        verbose_name_plural = "订单"
        indexes = [
            models.Index(fields=["buyer", "status"]),
            models.Index(fields=["seller", "status"]),
            models.Index(fields=["listing", "status"]),
            models.Index(fields=["status", "payment_deadline"]),
        ]

    class OrderStatus(models.TextChoices):
        """订单生命周期状态。"""

        PENDING_PAYMENT = "pending_payment", "待支付"
        CANCELLED = "cancelled", "已取消"
        AWAITING_SHIPMENT = "awaiting_shipment", "待发货"
        AWAITING_RECEIPT = "awaiting_receipt", "待收货"
        SIGNED = "signed", "已签收"
        COMPLETED = "completed", "已完成"

    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="orders_as_buyer",
        verbose_name="买家",
    )
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="orders_as_seller",
        verbose_name="卖家",
    )
    listing = models.ForeignKey(
        "catalog.Listing",
        on_delete=models.SET_NULL,
        null=True,
        related_name="orders",
        verbose_name="关联商品",
    )
    # 快照字段
    buyer_display_name = models.CharField(max_length=20, verbose_name="买家名称")
    seller_display_name = models.CharField(max_length=20, verbose_name="卖家名称")
    listing_title_snapshot = models.CharField(max_length=50, verbose_name="商品名称")
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        verbose_name="订单状态",
        default=OrderStatus.PENDING_PAYMENT,
    )
    order_price = models.DecimalField(
        max_digits=8, decimal_places=2, verbose_name="订单价格"
    )
    payment_deadline = models.DateTimeField(verbose_name="截止时间")
    paid_at = models.DateTimeField(verbose_name="支付成功时间", null=True)
    shipped_at = models.DateTimeField(verbose_name="卖家确认发货时间", null=True)
    logistics_signed_due_at = models.DateTimeField(
        verbose_name="模拟物流到达时间", null=True
    )
    signed_at = models.DateTimeField(verbose_name="签收时间", null=True)
    completed_at = models.DateTimeField(verbose_name="签收时间", null=True)
    cancelled_at = models.DateTimeField(verbose_name="取消时间", null=True)
    created_at = models.DateTimeField(verbose_name="创建时间", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="更新时间", auto_now=True)

    def __str__(self):
        """返回后台和调试输出中展示的订单摘要。"""

        return f"#{self.pk} {self.listing_title_snapshot}"
