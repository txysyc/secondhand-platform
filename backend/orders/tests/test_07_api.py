from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from catalog.models import Category, Listing, ListingImage
from orders.admin import OrderAdmin
from orders.models import Order
from orders.selectors import get_buyer_orders, get_seller_orders
from orders.services import (
    cancel_expired_pending_orders,
    auto_complete_eligible_physical_order,
    auto_complete_eligible_virtual_order,
    confirm_order_delivery,
    confirm_order_receipt,
    create_order,
    mark_due_physical_orders_signed,
    pay_order,
)
from orders import tasks as order_tasks
from users.models import UserAddress

User = get_user_model()


pytestmark = pytest.mark.django_db

class TestOrdersApi:
    """P5 订单 API 测试。"""

    @pytest.fixture(autouse=True)
    def _setup_context(self, api_client, auth_headers):
        self.api_client = api_client
        self.auth_headers = auth_headers
        self.buyer = User.objects.create_user(
            username="obuyer",
            email="order_buyer@example.com",
            password="StrongPass123",
        )
        self.seller = User.objects.create_user(
            username="oseller",
            email="order_seller@example.com",
            password="StrongPass123",
        )
        self.other = User.objects.create_user(
            username="oother",
            email="order_other@example.com",
            password="StrongPass123",
        )
        self.category = Category.objects.create(name="订单分类")
        self.listing = self.create_listing()
        self.address = self.create_address(self.buyer)
        self.other_address = self.create_address(
            self.other,
            recipient_name="其他买家",
            phone="13900139000",
        )
        self.idempotency_index = 0

    def create_address(self, user, **overrides):
        data = {
            "user": user,
            "recipient_name": "订单买家",
            "phone": "13800138000",
            "province": "广东省",
            "city": "深圳市",
            "district": "南山区",
            "detail_address": "订单地址1号",
            "is_default": True,
        }
        data.update(overrides)
        return UserAddress.objects.create(**data)

    def create_order_headers(self, user):
        self.idempotency_index += 1
        return {
            **self.auth_headers(user),
            "HTTP_IDEMPOTENCY_KEY": f"order-key-{self.idempotency_index:04d}",
        }

    def create_listing(self, **overrides):
        data = {
            "owner": self.seller,
            "category": self.category,
            "title": "订单商品",
            "item_type": Listing.ItemType.PHYSICAL,
            "status": Listing.Status.ACTIVE,
            "price": Decimal("199.00"),
            "condition": Listing.Condition.GOOD,
            "description": "订单商品描述",
            "delivery_notes": "面交",
            "physical_delivery_method": Listing.PhysicalDeliveryMethod.MEETUP,
            "published_at": timezone.now(),
        }
        data.update(overrides)
        return Listing.objects.create(**data)

    def create_order(self, **overrides):
        data = {
            "buyer": self.buyer,
            "seller": self.seller,
            "listing": self.listing,
            "buyer_display_name": self.buyer.username,
            "seller_display_name": self.seller.username,
            "listing_title_snapshot": self.listing.title,
            "order_price": self.listing.price,
            "status": Order.OrderStatus.PENDING_PAYMENT,
            "payment_deadline": timezone.now() + timedelta(minutes=15),
        }
        data.update(overrides)
        return Order.objects.create(**data)

    def test_create_order_requires_login(self):
        response = self.api_client.post(
            reverse("api:orders_create", kwargs={"listing_id": self.listing.id}),
            format="json",
        )

        assert response.status_code == 401

    def test_buyer_can_create_order_for_active_listing(self):
        response = self.api_client.post(
            reverse("api:orders_create", kwargs={"listing_id": self.listing.id}),
            data={"address_id": self.address.id},
            format="json",
            **self.create_order_headers(self.buyer),
        )

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == Order.OrderStatus.PENDING_PAYMENT
        assert body["viewer_role"] == "buyer"
        assert body["available_actions"] == ["pay"]
        assert "listing_image_snapshot" in body
        assert body["shipping_address_snapshot"]["recipient_name"] == "订单买家"
        assert Order.objects.filter(
            pk=body["id"],
            buyer=self.buyer,
            seller=self.seller,
            listing=self.listing,
        ).exists() is True

    def test_create_order_rejects_self_purchase_and_non_active_listing(self):
        self_purchase_response = self.api_client.post(
            reverse("api:orders_create", kwargs={"listing_id": self.listing.id}),
            data={"address_id": self.address.id},
            format="json",
            **self.create_order_headers(self.seller),
        )
        withdrawn = self.create_listing(status=Listing.Status.WITHDRAWN)
        withdrawn_response = self.api_client.post(
            reverse("api:orders_create", kwargs={"listing_id": withdrawn.id}),
            data={"address_id": self.address.id},
            format="json",
            **self.create_order_headers(self.buyer),
        )

        assert self_purchase_response.status_code == 403
        assert self_purchase_response.json()["message"] == "用户不能购买自己发布的商品"
        assert withdrawn_response.status_code == 400
        assert withdrawn_response.json()["message"] == "该商品不能购买"

    def test_create_order_rejects_duplicate_unexpired_pending_order(self):
        self.create_order()

        response = self.api_client.post(
            reverse("api:orders_create", kwargs={"listing_id": self.listing.id}),
            data={"address_id": self.other_address.id},
            format="json",
            **self.create_order_headers(self.other),
        )

        assert response.status_code == 400
        assert response.json()["message"] == "该商品已有待支付订单，请稍后再试"

    def test_create_physical_order_requires_address(self):
        response = self.api_client.post(
            reverse("api:orders_create", kwargs={"listing_id": self.listing.id}),
            format="json",
            **self.create_order_headers(self.buyer),
        )

        assert response.status_code == 400
        assert response.json()["message"] == "实体商品订单必须选择收货地址"

    def test_create_order_rejects_other_users_address(self):
        response = self.api_client.post(
            reverse("api:orders_create", kwargs={"listing_id": self.listing.id}),
            data={"address_id": self.other_address.id},
            format="json",
            **self.create_order_headers(self.buyer),
        )

        assert response.status_code == 400
        assert response.json()["message"] == "收货地址不存在或无权使用"

    def test_create_virtual_order_without_address_and_snapshot_is_null(self):
        virtual_listing = self.create_listing(
            title="虚拟商品",
            item_type=Listing.ItemType.VIRTUAL,
            condition=None,
            physical_delivery_method=None,
        )

        response = self.api_client.post(
            reverse("api:orders_create", kwargs={"listing_id": virtual_listing.id}),
            format="json",
            **self.create_order_headers(self.buyer),
        )

        assert response.status_code == 201
        assert response.json()["shipping_address_snapshot"] is None

    def test_create_order_requires_idempotency_key(self):
        response = self.api_client.post(
            reverse("api:orders_create", kwargs={"listing_id": self.listing.id}),
            data={"address_id": self.address.id},
            format="json",
            **self.auth_headers(self.buyer),
        )

        assert response.status_code == 400
        assert response.json()["message"] == "缺少幂等请求头"

    def test_same_idempotency_key_returns_same_order(self):
        headers = {
            **self.auth_headers(self.buyer),
            "HTTP_IDEMPOTENCY_KEY": "same-key-0001",
        }

        first_response = self.api_client.post(
            reverse("api:orders_create", kwargs={"listing_id": self.listing.id}),
            data={"address_id": self.address.id},
            format="json",
            **headers,
        )
        second_response = self.api_client.post(
            reverse("api:orders_create", kwargs={"listing_id": self.listing.id}),
            data={"address_id": self.address.id},
            format="json",
            **headers,
        )

        assert first_response.status_code == 201
        assert second_response.status_code == 200
        assert second_response.json()["id"] == first_response.json()["id"]

    def test_buyer_and_seller_lists_only_return_related_orders(self):
        buyer_order = self.create_order()
        seller_order = self.create_order(
            buyer=self.other,
            buyer_display_name=self.other.username,
        )
        unrelated_seller = User.objects.create_user(
            username="other_sell",
            email="unrelated_seller@example.com",
            password="StrongPass123",
        )
        unrelated_listing = self.create_listing(owner=unrelated_seller)
        self.create_order(
            buyer=self.other,
            seller=unrelated_seller,
            listing=unrelated_listing,
            seller_display_name=unrelated_seller.username,
        )

        buyer_response = self.api_client.get(
            reverse("api:orders_buyer"),
            **self.auth_headers(self.buyer),
        )
        seller_response = self.api_client.get(
            reverse("api:orders_seller"),
            **self.auth_headers(self.seller),
        )

        assert buyer_response.status_code == 200
        assert [item["id"] for item in buyer_response.json()["results"]] == [
            buyer_order.id
        ]
        assert seller_response.status_code == 200
        assert sorted(item["id"] for item in seller_response.json()["results"]) == sorted(
            [buyer_order.id, seller_order.id]
        )

    def test_order_list_filters_and_sorts_by_status_keyword_price_and_time(self):
        target = self.create_order(
            listing_title_snapshot="蓝牙耳机订单",
            order_price=Decimal("88.00"),
            status=Order.OrderStatus.AWAITING_SHIPMENT,
        )
        Order.objects.filter(pk=target.pk).update(
            created_at=timezone.now() - timedelta(days=2)
        )
        wrong_status = self.create_order(
            listing_title_snapshot="蓝牙键盘订单",
            order_price=Decimal("90.00"),
            status=Order.OrderStatus.PENDING_PAYMENT,
        )
        too_expensive = self.create_order(
            listing_title_snapshot="蓝牙音箱订单",
            order_price=Decimal("188.00"),
            status=Order.OrderStatus.AWAITING_SHIPMENT,
        )

        response = self.api_client.get(
            reverse("api:orders_buyer"),
            {
                "q": " 蓝牙 ",
                "status": Order.OrderStatus.AWAITING_SHIPMENT,
                "min_price": "50",
                "max_price": "100",
                "created_after": (timezone.now() - timedelta(days=3)).isoformat(),
                "created_before": (timezone.now() - timedelta(days=1)).isoformat(),
                "sort": "price_asc",
            },
            **self.auth_headers(self.buyer),
        )

        ids = [item["id"] for item in response.json()["results"]]
        assert response.status_code == 200
        assert ids == [target.id]
        assert wrong_status.id not in ids
        assert too_expensive.id not in ids

    def test_order_list_invalid_filter_and_page_size_cap(self):
        for index in range(55):
            self.create_order(listing_title_snapshot=f"分页订单{index}")

        invalid_price_response = self.api_client.get(
            reverse("api:orders_buyer"),
            {"min_price": "100", "max_price": "10"},
            **self.auth_headers(self.buyer),
        )
        invalid_time_response = self.api_client.get(
            reverse("api:orders_buyer"),
            {
                "created_after": "2026-05-02T10:00:00+08:00",
                "created_before": "2026-05-01T10:00:00+08:00",
            },
            **self.auth_headers(self.buyer),
        )
        page_response = self.api_client.get(
            reverse("api:orders_buyer"),
            {"page_size": "999"},
            **self.auth_headers(self.buyer),
        )
        keyword_response = self.api_client.get(
            reverse("api:orders_buyer"),
            {"q": "订" * 51},
            **self.auth_headers(self.buyer),
        )

        assert invalid_price_response.status_code == 400
        assert "最高价格不得低于最低价格" in invalid_price_response.json()["message"]
        assert invalid_time_response.status_code == 400
        assert "创建时间截止不得早于创建时间起始" in invalid_time_response.json()["message"]
        assert keyword_response.status_code == 400
        assert "搜索关键词不能超过50个字符" in keyword_response.json()["message"]
        assert page_response.status_code == 200
        assert page_response.json()["page_size"] == 50
        assert len(page_response.json()["results"]) == 50

    def test_order_detail_requires_participant_and_exposes_display_fields(self):
        order = self.create_order()

        other_response = self.api_client.get(
            reverse("api:orders_detail", kwargs={"pk": order.id}),
            **self.auth_headers(self.other),
        )
        buyer_response = self.api_client.get(
            reverse("api:orders_detail", kwargs={"pk": order.id}),
            **self.auth_headers(self.buyer),
        )

        assert other_response.status_code == 403
        assert buyer_response.status_code == 200
        body = buyer_response.json()
        assert body["viewer_role"] == "buyer"
        assert body["is_expired"] is False
        assert body["available_actions"] == ["pay"]
        assert body["listing_title_snapshot"] == "订单商品"
        assert "images" in body["listing"]

    def test_expired_order_detail_hides_pay_action(self):
        order = self.create_order(payment_deadline=timezone.now() - timedelta(minutes=1))

        response = self.api_client.get(
            reverse("api:orders_detail", kwargs={"pk": order.id}),
            **self.auth_headers(self.buyer),
        )

        assert response.status_code == 200
        assert response.json()["is_expired"] is True
        assert response.json()["available_actions"] == []

    def test_buyer_can_pay_and_repeat_or_expired_payment_fail(self):
        order = self.create_order()

        paid_response = self.api_client.post(
            reverse("api:orders_pay", kwargs={"pk": order.id}),
            **self.auth_headers(self.buyer),
        )
        repeat_response = self.api_client.post(
            reverse("api:orders_pay", kwargs={"pk": order.id}),
            **self.auth_headers(self.buyer),
        )
        expired_listing = self.create_listing(title="过期支付商品")
        expired_order = self.create_order(
            listing=expired_listing,
            listing_title_snapshot=expired_listing.title,
            payment_deadline=timezone.now() - timedelta(minutes=1),
        )
        expired_response = self.api_client.post(
            reverse("api:orders_pay", kwargs={"pk": expired_order.id}),
            **self.auth_headers(self.buyer),
        )

        assert paid_response.status_code == 200
        assert paid_response.json()["status"] == Order.OrderStatus.AWAITING_SHIPMENT
        assert paid_response.json()["available_actions"] == []
        assert repeat_response.status_code == 400
        assert repeat_response.json()["message"] == "该订单已支付或已取消，请勿重复购买"
        assert expired_response.status_code == 400
        assert expired_response.json()["message"] == "订单已超时，系统已自动取消"

    def test_seller_can_confirm_delivery_once(self):
        order = self.create_order(
            status=Order.OrderStatus.AWAITING_SHIPMENT,
            paid_at=timezone.now(),
        )
        self.listing.status = Listing.Status.RESERVED
        self.listing.save(update_fields=["status"])

        response = self.api_client.post(
            reverse("api:orders_confirm_delivery", kwargs={"pk": order.id}),
            **self.auth_headers(self.seller),
        )
        repeat_response = self.api_client.post(
            reverse("api:orders_confirm_delivery", kwargs={"pk": order.id}),
            **self.auth_headers(self.seller),
        )

        assert response.status_code == 200
        assert response.json()["status"] == Order.OrderStatus.AWAITING_RECEIPT
        assert response.json()["viewer_role"] == "seller"
        assert response.json()["available_actions"] == []
        assert repeat_response.status_code == 400
        assert repeat_response.json()["message"] == "订单不是待发货状态"

    def test_wrong_user_cannot_confirm_delivery_or_receipt(self):
        order = self.create_order(
            status=Order.OrderStatus.AWAITING_SHIPMENT,
            paid_at=timezone.now(),
        )
        self.listing.status = Listing.Status.RESERVED
        self.listing.save(update_fields=["status"])

        buyer_delivery_response = self.api_client.post(
            reverse("api:orders_confirm_delivery", kwargs={"pk": order.id}),
            **self.auth_headers(self.buyer),
        )
        seller_receipt_response = self.api_client.post(
            reverse("api:orders_confirm_receipt", kwargs={"pk": order.id}),
            **self.auth_headers(self.seller),
        )

        assert buyer_delivery_response.status_code == 403
        assert seller_receipt_response.status_code == 403

    def test_buyer_can_confirm_receipt_and_invalid_status_fails(self):
        order = self.create_order(
            status=Order.OrderStatus.AWAITING_RECEIPT,
            paid_at=timezone.now() - timedelta(days=1),
            shipped_at=timezone.now(),
        )
        self.listing.status = Listing.Status.RESERVED
        self.listing.save(update_fields=["status"])
        pending_order = self.create_order()

        response = self.api_client.post(
            reverse("api:orders_confirm_receipt", kwargs={"pk": order.id}),
            **self.auth_headers(self.buyer),
        )
        invalid_response = self.api_client.post(
            reverse("api:orders_confirm_receipt", kwargs={"pk": pending_order.id}),
            **self.auth_headers(self.buyer),
        )

        assert response.status_code == 200
        assert response.json()["status"] == Order.OrderStatus.COMPLETED
        # 已完成且未评分的买家订单应暴露一次性评分动作。
        assert response.json()["available_actions"] == ["rate"]
        self.listing.refresh_from_db()
        assert self.listing.status == Listing.Status.SOLD
        assert invalid_response.status_code == 400
        assert invalid_response.json()["message"] == "实体商品订单不能确认收货"

    def test_api_does_not_change_celery_task_behavior(self):
        with patch.object(order_tasks, "cancel_expired_pending_orders", return_value=2):
            assert order_tasks.cancel_expired_pending_orders_task() == 2
        with patch.object(order_tasks, "mark_due_physical_orders_signed", return_value=1):
            assert order_tasks.mark_due_physical_orders_signed_task() == 1
        with patch.object(order_tasks, "auto_complete_eligible_physical_order", return_value=3), patch.object(
            order_tasks,
            "auto_complete_eligible_virtual_order",
            return_value=4,
        ):
            assert order_tasks.auto_complete_eligible_orders_task() == 7



