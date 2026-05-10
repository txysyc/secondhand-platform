from django.db import models
from django.conf import settings


# Create your models here.
class Category(models.Model):
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
        return f"{self.name}"


class Listing(models.Model):
    class Meta:
        verbose_name = "商品列表"
        verbose_name_plural = "商品列表"

    class ItemType(models.TextChoices):
        PHYSICAL = "physical", "实体商品"
        VIRTUAL = "virtual", "虚拟商品"

    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        ACTIVE = "active", "在售"
        RESERVED = "reserved", "交易占用"
        SOLD = "sold", "已售出"
        WITHDRAWN = "withdrawn", "已下架"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="所属用户",
        related_name="listing",
        on_delete=models.PROTECT,
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
        verbose_name="商品状态", choices=Status.choices, null=False
    )
    # max_digits：允许多少位数字，decimal_places：小数点位数
    price = models.DecimalField(
        verbose_name="价格", max_digits=8, decimal_places=2, null=False, blank=False
    )
    description = models.TextField(verbose_name="描述")
    created_at = models.DateTimeField(verbose_name="创建时间", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="更新时间", auto_now=True)

    def __str__(self):
        return f"{self.title}"
