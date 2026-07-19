from decimal import Decimal

import pytest
from io import BytesIO

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.exceptions import PermissionDenied, ValidationError

from catalog.admin import CategoryAdmin, ListingAdmin
from catalog.filters import ListingFilterSet
from catalog.models import Category, Listing, ListingImage
from catalog.selectors import (
    _active_category_ids_cache_key,
    get_active_categories,
    get_active_category_ids,
    get_public_listing_queryset,
    get_visible_listing_detail_queryset,
)
from orders.models import Order
from catalog.services import (
    ACTION_RESTORE_ACTIVE,
    ACTION_WITHDRAW,
    change_listing_status,
    delete_listing,
    publish_listing,
)
from users.models import User


pytestmark = pytest.mark.django_db

class TestCategorySelector:
    """分类读取查询测试。"""

    def test_get_active_categories_returns_only_active_categories_in_stable_order(self):
        first = Category.objects.create(name="数码产品")
        Category.objects.create(name="停用分类", is_active=False)
        second = Category.objects.create(name="生活用品")

        categories = list(get_active_categories())

        assert categories == [first, second]
        assert "停用分类" not in [category.name for category in categories]

    def test_get_active_category_ids_refreshes_stale_cache(self):
        """启用分类 ID 缓存陈旧时自动刷新，避免公开列表被旧分类 ID 清空。"""

        first = Category.objects.create(name="缓存自愈分类一")
        second = Category.objects.create(name="缓存自愈分类二")
        cache_key = _active_category_ids_cache_key()
        cache.set(cache_key, [999999])

        ids = get_active_category_ids()

        assert ids == [first.id, second.id]
        assert cache.get(cache_key) == [first.id, second.id]


