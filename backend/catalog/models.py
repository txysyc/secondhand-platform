from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

Max_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB


class Category(models.Model):
    """商品分类模型。"""

    class Meta:
        verbose_name = "商品分类"
        verbose_name_plural = "商品分类"
        ordering = ["name"]

    name = models.CharField(
        verbose_name="分类名称", null=False, max_length=20, unique=True
    )
    is_active = models.BooleanField(verbose_name="是否启用", null=False, default=True)
    created_at = models.DateTimeField(verbose_name="创建时间", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="更新时间", auto_now=True)

    def __str__(self):
        """返回后台、API 和调试输出中展示的分类名称。"""

        return f"{self.name}"


def valid_virtual_until_time(value):
    """模型层兜底校验虚拟商品有效期，必填规则由 API serializer 处理。"""

    if value < timezone.localdate():
        raise ValidationError("过期时间不能早于当前日期")


class Listing(models.Model):
    """平台商品模型，保存发布内容、交易状态和类型差异字段。"""

    class Meta:
        verbose_name = "商品列表"
        verbose_name_plural = "商品列表"
        indexes = [
            # 公开列表默认只看在售商品，并按发布时间倒序展示。
            models.Index(
                fields=["status", "-published_at"],
                name="listing_status_pub_idx",
            ),
            # 分类页在公开列表中同样按发布时间倒序展示。
            models.Index(fields=["category", "-published_at"], name="listing_cat_pub_idx"),
            # 商品类型筛选会叠加发布时间排序。
            models.Index(
                fields=["item_type", "-published_at"],
                name="listing_type_pub_idx",
            ),
            # 价格区间筛选和价格排序共用单列索引。
            models.Index(fields=["price"], name="listing_price_idx"),
            # 发布时间区间筛选和默认排序共用单列索引。
            models.Index(fields=["published_at"], name="listing_pub_idx"),
            # 我的商品管理默认按用户和更新时间倒序展示。
            models.Index(fields=["owner", "-updated_at"], name="listing_owner_updated_idx"),
            # 我的商品管理状态筛选会叠加更新时间排序。
            models.Index(
                fields=["owner", "status", "-updated_at"],
                name="listing_owner_status_idx",
            ),
        ]

    class ItemType(models.TextChoices):
        """商品类型，独立于业务分类，避免把“实体/虚拟”混入分类。"""

        PHYSICAL = "physical", "实体商品"
        VIRTUAL = "virtual", "虚拟商品"

    class Status(models.TextChoices):
        """商品生命周期状态；草稿创建流程默认写入 DRAFT。"""

        DRAFT = "draft", "草稿"
        ACTIVE = "active", "在售"
        RESERVED = "reserved", "交易占用"
        SOLD = "sold", "已售出"
        WITHDRAWN = "withdrawn", "已下架"

    class Condition(models.TextChoices):
        """实体商品成色选项。"""

        NEW = "new", "全新"
        LIKE_NEW = "like_new", "几乎全新"
        GOOD = "good", "轻微使用痕迹"
        FAIR = "fair", "明显使用痕迹"

    class PhysicalDeliveryMethod(models.TextChoices):
        """实体商品支持的交付方式。"""

        MEETUP = "meetup", "线下自提/面交"
        SHIPPING = "shipping", "快递发货"
        BOTH = "both", "均可"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="所属用户",
        related_name="listing",
        on_delete=models.CASCADE,
    )
    category = models.ForeignKey(
        "Category",
        verbose_name="商品分类",
        related_name="listing",
        on_delete=models.PROTECT,
    )
    title = models.CharField(verbose_name="标题", max_length=50, null=False)
    item_type = models.CharField(
        verbose_name="商品类型", choices=ItemType.choices, null=False, blank=False
    )
    status = models.CharField(
        verbose_name="商品状态",
        choices=Status.choices,
        null=False,
        default=Status.DRAFT,
    )
    # max_digits：允许多少位数字，decimal_places：小数点位数
    price = models.DecimalField(
        verbose_name="价格", max_digits=8, decimal_places=2, null=False, blank=False
    )
    description = models.TextField(verbose_name="描述")
    created_at = models.DateTimeField(verbose_name="创建时间", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="更新时间", auto_now=True)
    published_at = models.DateTimeField(verbose_name="发布时间", null=True, blank=True)
    condition = models.CharField(
        verbose_name="成色",
        choices=Condition.choices,
        max_length=100,
        null=True,
        blank=True,
    )
    # 通用交付说明，实体商品和虚拟商品共用，不随商品类型切换清空。
    delivery_notes = models.TextField(
        verbose_name="交付说明", null=False, blank=True, default=""
    )
    # 实体商品差异字段。
    physical_delivery_method = models.CharField(
        verbose_name="实体商品交付方法",
        choices=PhysicalDeliveryMethod.choices,
        max_length=300,
        null=True,
        blank=True,
    )
    # 虚拟商品差异字段。
    virtual_valid_until = models.DateField(
        verbose_name="到期时间",
        null=True,
        blank=True,
        validators=[valid_virtual_until_time],
    )

    def __str__(self):
        """返回后台和调试输出中展示的商品标题。"""

        return f"{self.title}"


def valid_image_size(value):
    """限制单张商品图片大小。
    """

    if value.size > Max_IMAGE_SIZE:
        raise ValidationError("图片大小大于5MB")


class ListingImage(models.Model):
    """商品图片模型，按 sort_order 维护同一商品下的展示顺序。"""

    class Meta:
        verbose_name = "商品图片"
        verbose_name_plural = "商品图片"
        ordering = ["sort_order", "id"]

    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        verbose_name="所属商品",
        related_name="images",
    )
    image = models.ImageField(
        verbose_name="商品图片",
        upload_to="listings/%Y/%m/%d",
        validators=[valid_image_size],
    )
    created_at = models.DateTimeField(verbose_name="创建时间", auto_now_add=True)
    sort_order = models.PositiveIntegerField(
        verbose_name="排序", default=0
    )  # 对上商品图片进行排序

    def __str__(self):
        """返回后台中展示的商品图片描述。"""

        return f"{self.listing}的图片"
