"""catalog Redis 缓存防护 pytest 测试。"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from catalog.cache import get_active_category_payload
from catalog.models import Category, Listing

User = get_user_model()
pytestmark = pytest.mark.django_db


class TestCatalogCache:
    """验证分类与匿名公开商品详情缓存的可用性和失效策略。"""

    @pytest.fixture(autouse=True)
    def _setup_context(self, api_client):
        """构造公开商品和独立缓存空间。"""

        cache.clear()
        self.api_client = api_client
        self.owner = User.objects.create_user(
            username="缓存卖家",
            email="cache-seller@example.com",
            password="StrongPass123",
        )
        self.category = Category.objects.create(name="缓存分类")
        self.listing = Listing.objects.create(
            owner=self.owner,
            category=self.category,
            title="缓存商品",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.ACTIVE,
            price=Decimal("66.00"),
            condition=Listing.Condition.GOOD,
            description="匿名公开详情缓存测试",
            delivery_notes="面交",
            physical_delivery_method=Listing.PhysicalDeliveryMethod.MEETUP,
            published_at=timezone.now(),
        )

    def test_category_payload_hit_does_not_query_database(self, django_assert_num_queries):
        """分类快照命中后无需再次读取分类表。"""

        assert get_active_category_payload() == [{"id": self.category.id, "name": "缓存分类"}]

        with django_assert_num_queries(0):
            assert get_active_category_payload() == [
                {"id": self.category.id, "name": "缓存分类"}
            ]

    def test_anonymous_listing_detail_is_cached_and_invalidated_on_update(
        self,
        django_assert_num_queries,
    ):
        """匿名详情缓存命中零 SQL，商品更新后读取最新快照。"""

        url = reverse("api:catalog_listing_detail", kwargs={"pk": self.listing.id})
        first_response = self.api_client.get(url)

        assert first_response.status_code == 200
        with django_assert_num_queries(0):
            cached_response = self.api_client.get(url)
        assert cached_response.json()["title"] == "缓存商品"

        self.listing.title = "更新后的缓存商品"
        self.listing.save(update_fields=["title", "updated_at"])
        refreshed_response = self.api_client.get(url)

        assert refreshed_response.status_code == 200
        assert refreshed_response.json()["title"] == "更新后的缓存商品"

    def test_missing_listing_uses_short_lived_empty_cache(self, django_assert_num_queries):
        """不存在商品的第二次匿名请求命中空值哨兵而不访问数据库。"""

        url = reverse("api:catalog_listing_detail", kwargs={"pk": 999999})
        assert self.api_client.get(url).status_code == 404

        with django_assert_num_queries(0):
            assert self.api_client.get(url).status_code == 404
