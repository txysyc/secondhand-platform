"""catalog 应用缓存失效信号。"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from catalog.models import Category
from catalog.selectors import clear_active_category_cache


@receiver([post_save, post_delete], sender=Category)
def clear_active_categories_cache(sender, instance, **kwargs):
    """分类启停、新增或删除后清理启用分类缓存。"""

    clear_active_category_cache()
