from decimal import Decimal

import pytest
from io import BytesIO

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.exceptions import PermissionDenied, ValidationError

from catalog.admin import CategoryAdmin, ListingAdmin
from catalog.filters import ListingFilterSet
from catalog.models import Category, Listing, ListingImage
from catalog.selectors import (
    apply_public_listing_sort,
    get_active_categories,
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

class TestListingFilterSet:
    """公开商品列表 FilterSet 测试。"""

    @pytest.fixture(autouse=True)
    def _setup_listing_filter_context(self):
        """构造公开商品筛选测试需要的卖家和分类。"""

        self.user = get_user_model().objects.create_user(
            username="fltseller",
            email="filter_seller@example.com",
            password="StrongPass123",
        )
        self.category = Category.objects.create(name="筛选分类")
        self.other_category = Category.objects.create(name="筛选另一分类")
        self.inactive_category = Category.objects.create(name="筛选停用分类", is_active=False)

    def make_listing(self, **overrides):
        """创建默认可公开展示的筛选测试商品。"""

        data = {
            "owner": self.user,
            "category": self.category,
            "title": "筛选商品",
            "item_type": Listing.ItemType.PHYSICAL,
            "status": Listing.Status.ACTIVE,
            "price": Decimal("30.00"),
            "condition": Listing.Condition.GOOD,
            "description": "公开展示商品",
            "delivery_notes": "面交",
            "physical_delivery_method": Listing.PhysicalDeliveryMethod.MEETUP,
            "published_at": timezone.now(),
        }
        data.update(overrides)
        return Listing.objects.create(**data)

    def filter_results(self, params):
        """用公开基础查询执行 FilterSet，并返回筛选后的商品列表。"""

        filterset = ListingFilterSet(data=params, queryset=get_public_listing_queryset())
        assert filterset.is_valid(), filterset.errors
        return list(filterset.qs)

    def test_keyword_matches_title_or_description(self):
        match_title = self.make_listing(title="蓝牙耳机", description="无关描述")
        match_desc = self.make_listing(title="无关标题", description="蓝牙音箱描述")
        no_match = self.make_listing(title="无关标题", description="无关描述")

        results = self.filter_results({"q": " 蓝牙 "})

        assert match_title in results
        assert match_desc in results
        assert no_match not in results

    def test_blank_keyword_equals_no_search(self):
        first = self.make_listing(title="蓝牙耳机")
        second = self.make_listing(title="普通键盘")

        results = self.filter_results({"q": "   "})

        assert first in results
        assert second in results

    def test_too_long_keyword_returns_chinese_error(self):
        filterset = ListingFilterSet(
            data={"q": "蓝" * 51},
            queryset=get_public_listing_queryset(),
        )

        assert filterset.is_valid() is False
        assert "搜索关键词不能超过50个字符" in str(filterset.errors)

    def test_category_filter(self):
        target = self.make_listing(title="目标分类商品", category=self.category)
        other = self.make_listing(title="其他分类商品", category=self.other_category)

        results = self.filter_results({"category": self.category.id})

        assert target in results
        assert other not in results

    def test_item_type_filter(self):
        physical = self.make_listing(title="实体", item_type=Listing.ItemType.PHYSICAL)
        virtual = self.make_listing(title="虚拟", item_type=Listing.ItemType.VIRTUAL)

        results = self.filter_results({"item_type": "virtual"})

        assert physical not in results
        assert virtual in results

    def test_price_range_filter(self):
        cheap = self.make_listing(title="便宜", price=Decimal("10.00"))
        mid = self.make_listing(title="中等", price=Decimal("50.00"))
        expensive = self.make_listing(title="贵", price=Decimal("200.00"))

        results = self.filter_results({"min_price": "20", "max_price": "100"})

        assert cheap not in results
        assert mid in results
        assert expensive not in results

    def test_published_range_filter(self):
        old = self.make_listing(
            title="旧商品",
            published_at=timezone.now() - timezone.timedelta(days=5),
        )
        mid = self.make_listing(
            title="中间商品",
            published_at=timezone.now() - timezone.timedelta(days=2),
        )
        new = self.make_listing(title="新商品", published_at=timezone.now())

        results = self.filter_results({
            "published_after": (timezone.now() - timezone.timedelta(days=3)).strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "published_before": (timezone.now() - timezone.timedelta(days=1)).strftime(
                "%Y-%m-%dT%H:%M"
            ),
        })

        assert old not in results
        assert mid in results
        assert new not in results

    def test_published_before_date_includes_whole_day(self):
        target_day = timezone.localdate() - timezone.timedelta(days=1)
        target_time = timezone.make_aware(
            timezone.datetime.combine(target_day, timezone.datetime.min.time()),
            timezone.get_current_timezone(),
        )
        target = self.make_listing(
            title="当天商品",
            published_at=target_time.replace(hour=18, minute=30, second=0),
        )

        results = self.filter_results({
            "published_before": target.published_at.strftime("%Y-%m-%d"),
        })

        assert target in results

    def test_invalid_price_or_published_range_returns_chinese_error(self):
        price_filterset = ListingFilterSet(
            data={"min_price": "100", "max_price": "10"},
            queryset=get_public_listing_queryset(),
        )
        time_filterset = ListingFilterSet(
            data={
                "published_after": "2026-05-02T10:00",
                "published_before": "2026-05-01T10:00",
            },
            queryset=get_public_listing_queryset(),
        )

        assert price_filterset.is_valid() is False
        assert "最高价格不得低于最低价格" in str(price_filterset.errors)
        assert time_filterset.is_valid() is False
        assert "发布时间截止不得早于发布时间起始" in str(time_filterset.errors)

    def test_combined_filters(self):
        target = self.make_listing(
            title="蓝牙耳机",
            item_type=Listing.ItemType.PHYSICAL,
            price=Decimal("50.00"),
        )
        wrong_type = self.make_listing(
            title="蓝牙会员",
            item_type=Listing.ItemType.VIRTUAL,
            price=Decimal("50.00"),
        )
        wrong_price = self.make_listing(
            title="蓝牙音箱",
            item_type=Listing.ItemType.PHYSICAL,
            price=Decimal("500.00"),
        )

        results = self.filter_results(
            {
                "q": "蓝牙",
                "item_type": "physical",
                "min_price": "10",
                "max_price": "100",
            }
        )

        assert results == [target]


