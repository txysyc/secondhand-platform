"""catalog 应用缓存失效信号。"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from catalog.cache import (
    clear_active_category_cache,
    invalidate_public_listing_detail_cache,
)
from catalog.models import Category, Listing, ListingImage


@receiver([post_save, post_delete], sender=Category)
def clear_active_categories_cache(sender, instance, **kwargs):
    """分类启停、新增或删除后立即清理启用分类缓存。"""

    clear_active_category_cache()


@receiver([post_save, post_delete], sender=Listing)
def clear_listing_detail_cache(sender, instance, **kwargs):
    """商品状态或展示字段变更后失效对应匿名详情缓存。"""

    invalidate_public_listing_detail_cache(instance.pk)


@receiver([post_save, post_delete], sender=ListingImage)
def clear_listing_image_detail_cache(sender, instance, **kwargs):
    """商品图片变更后失效所属商品的匿名详情缓存。"""

    invalidate_public_listing_detail_cache(instance.listing_id)
