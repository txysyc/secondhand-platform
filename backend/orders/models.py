from django.core.validators import MaxValueValidator, MinValueValidator
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
            # 买家订单列表默认按创建时间倒序展示。
            models.Index(fields=["buyer", "-created_at"], name="order_buyer_created_idx"),
            # 卖家订单列表默认按创建时间倒序展示。
            models.Index(fields=["seller", "-created_at"], name="order_seller_created_idx"),
            # 买家订单状态筛选会叠加创建时间排序。
            models.Index(
                fields=["buyer", "status", "-created_at"],
                name="order_buyer_status_idx",
            ),
            # 卖家订单状态筛选会叠加创建时间排序。
            models.Index(
                fields=["seller", "status", "-created_at"],
                name="order_seller_status_idx",
            ),
            # 订单价格区间筛选和价格排序共用单列索引。
            models.Index(fields=["order_price"], name="order_price_idx"),
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
    listing_image_snapshot = models.URLField(
        verbose_name="商品首图快照",
        null=True,
        blank=True,
    )
    shipping_recipient_name = models.CharField(
        verbose_name="收货人快照",
        max_length=30,
        null=True,
        blank=True,
    )
    shipping_phone = models.CharField(
        verbose_name="手机号快照",
        max_length=20,
        null=True,
        blank=True,
    )
    shipping_province = models.CharField(
        verbose_name="省快照",
        max_length=30,
        null=True,
        blank=True,
    )
    shipping_city = models.CharField(
        verbose_name="市快照",
        max_length=30,
        null=True,
        blank=True,
    )
    shipping_district = models.CharField(
        verbose_name="区快照",
        max_length=30,
        null=True,
        blank=True,
    )
    shipping_detail_address = models.CharField(
        verbose_name="详细地址快照",
        max_length=200,
        null=True,
        blank=True,
    )
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


class OrderRating(models.Model):
    """买家对已完成订单卖家的不可修改星级评分。"""

    class Meta:
        verbose_name = "订单评分"
        verbose_name_plural = "订单评分"
        ordering = ["-created_at", "-id"]

    # 一对一约束从数据库层保证同一订单最多只能评分一次。
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="buyer_rating",
        verbose_name="订单",
    )
    score = models.PositiveSmallIntegerField(
        verbose_name="星级评分",
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    created_at = models.DateTimeField(verbose_name="评分时间", auto_now_add=True)

    def __str__(self):
        """返回后台和调试输出中展示的评分摘要。"""

        return f"订单#{self.order_id}：{self.score}星"
