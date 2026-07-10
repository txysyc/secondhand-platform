"""订单星级评分 pytest 测试。"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Listing
from orders.models import Order, OrderRating
from orders.selectors import get_buyer_orders
from orders.serializers import OrderSerializer
from orders.services import create_order_rating

User = get_user_model()
pytestmark = pytest.mark.django_db


class TestOrderRating:
    """验证订单评分的核心业务约束与 API 行为。"""

    @pytest.fixture(autouse=True)
    def _setup_context(self, api_client, auth_headers):
        """构造买家、卖家、无关用户与可完成订单。"""

        self.api_client = api_client
        self.auth_headers = auth_headers
        self.buyer = User.objects.create_user(
            username="评分买家",
            email="rating-buyer@example.com",
            password="StrongPass123",
        )
        self.seller = User.objects.create_user(
            username="评分卖家",
            email="rating-seller@example.com",
            password="StrongPass123",
        )
        self.other = User.objects.create_user(
            username="评分路人",
            email="rating-other@example.com",
            password="StrongPass123",
        )
        self.category = Category.objects.create(name="评分分类")

    def _create_completed_order(self, **overrides):
        """创建关联已售出商品的完成订单。"""

        listing = Listing.objects.create(
            owner=self.seller,
            category=self.category,
            title=f"评分商品{Order.objects.count()}",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.SOLD,
            price=Decimal("88.00"),
            condition=Listing.Condition.GOOD,
            description="订单评分测试商品",
            delivery_notes="面交",
            physical_delivery_method=Listing.PhysicalDeliveryMethod.MEETUP,
            published_at=timezone.now(),
        )
        data = {
            "buyer": self.buyer,
            "seller": self.seller,
            "listing": listing,
            "buyer_display_name": self.buyer.username,
            "seller_display_name": self.seller.username,
            "listing_title_snapshot": listing.title,
            "status": Order.OrderStatus.COMPLETED,
            "order_price": listing.price,
            "payment_deadline": timezone.now() - timedelta(days=2),
            "completed_at": timezone.now(),
        }
        data.update(overrides)
        return Order.objects.create(**data)

    def test_buyer_can_create_rating_and_same_score_retry_is_idempotent(self):
        """首次评分创建记录，同分重试返回同一不可修改评分。"""

        order = self._create_completed_order()
        rating, created = create_order_rating(self.buyer, order.id, 5)
        retry_rating, retry_created = create_order_rating(self.buyer, order.id, 5)

        assert created is True
        assert retry_created is False
        assert retry_rating.id == rating.id
        assert OrderRating.objects.filter(order=order, score=5).count() == 1

    def test_rating_rejects_non_buyer_non_completed_and_score_change(self):
        """评分必须由买家对完成订单提交，且提交后不能换分。"""

        order = self._create_completed_order()
        pending_order = self._create_completed_order(status=Order.OrderStatus.PENDING_PAYMENT)
        create_order_rating(self.buyer, order.id, 4)

        from rest_framework.exceptions import PermissionDenied, ValidationError

        with pytest.raises(PermissionDenied):
            create_order_rating(self.seller, order.id, 4)
        with pytest.raises(ValidationError, match="只有已完成订单可以评分"):
            create_order_rating(self.buyer, pending_order.id, 4)
        with pytest.raises(ValidationError, match="不能修改"):
            create_order_rating(self.buyer, order.id, 3)

    def test_rating_api_updates_order_action_and_returns_existing_rating(self):
        """评分接口返回最新订单数据，并在重复请求时保持幂等。"""

        order = self._create_completed_order()
        url = reverse("api:orders_rating", kwargs={"pk": order.id})

        first_response = self.api_client.post(
            url,
            data={"score": 5},
            format="json",
            **self.auth_headers(self.buyer),
        )
        retry_response = self.api_client.post(
            url,
            data={"score": 5},
            format="json",
            **self.auth_headers(self.buyer),
        )

        assert first_response.status_code == 201
        assert first_response.json()["buyer_rating"]["score"] == 5
        assert "rate" not in first_response.json()["available_actions"]
        assert retry_response.status_code == 200
        assert retry_response.json()["buyer_rating"]["score"] == 5

    def test_rating_api_rejects_unauthorized_and_invalid_score(self):
        """接口层同时覆盖认证、参与者权限和分数边界校验。"""

        order = self._create_completed_order()
        url = reverse("api:orders_rating", kwargs={"pk": order.id})

        anonymous_response = self.api_client.post(url, data={"score": 5}, format="json")
        other_response = self.api_client.post(
            url,
            data={"score": 5},
            format="json",
            **self.auth_headers(self.other),
        )
        invalid_response = self.api_client.post(
            url,
            data={"score": 6},
            format="json",
            **self.auth_headers(self.buyer),
        )

        assert anonymous_response.status_code == 401
        assert other_response.status_code == 403
        assert invalid_response.status_code == 400

    def test_public_profile_returns_seller_rating_summary(self):
        """公开主页只返回卖家自身的评分数量和平均分。"""

        first = self._create_completed_order()
        second = self._create_completed_order()
        create_order_rating(self.buyer, first.id, 4)
        create_order_rating(self.buyer, second.id, 5)

        response = self.api_client.get(
            reverse("api:users_public", kwargs={"user_id": self.seller.id})
        )

        assert response.status_code == 200
        assert response.json()["rating_summary"] == {
            "rating_count": 2,
            "average_score": 4.5,
        }

    def test_order_serializer_uses_prefetched_rating_relation(self, django_assert_num_queries):
        """订单列表在查询集加载后序列化评分不会再产生额外查询。"""

        order = self._create_completed_order()
        create_order_rating(self.buyer, order.id, 5)
        orders = list(get_buyer_orders(self.buyer))

        with django_assert_num_queries(0):
            serialized = OrderSerializer(orders, many=True).data

        assert serialized[0]["buyer_rating"]["score"] == 5
