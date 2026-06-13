from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.test import APIClient, APITestCase

from catalog.models import Category, Listing
from orders.models import Order
from orders import tasks as order_tasks


User = get_user_model()


class OrdersApiTests(APITestCase):
    """P5 订单 API 测试。"""

    def setUp(self):
        self.client = APIClient()
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

    def auth_headers(self, user):
        token = RefreshToken.for_user(user).access_token
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

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
        response = self.client.post(
            reverse("api:orders_create", kwargs={"listing_id": self.listing.id}),
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_buyer_can_create_order_for_active_listing(self):
        response = self.client.post(
            reverse("api:orders_create", kwargs={"listing_id": self.listing.id}),
            format="json",
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], Order.OrderStatus.PENDING_PAYMENT)
        self.assertEqual(body["viewer_role"], "buyer")
        self.assertEqual(body["available_actions"], ["pay"])
        self.assertEqual(Order.objects.count(), 1)

    def test_create_order_rejects_self_purchase_and_non_active_listing(self):
        self_purchase_response = self.client.post(
            reverse("api:orders_create", kwargs={"listing_id": self.listing.id}),
            format="json",
            **self.auth_headers(self.seller),
        )
        withdrawn = self.create_listing(status=Listing.Status.WITHDRAWN)
        withdrawn_response = self.client.post(
            reverse("api:orders_create", kwargs={"listing_id": withdrawn.id}),
            format="json",
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(self_purchase_response.status_code, 403)
        self.assertEqual(self_purchase_response.json()["message"], "用户不能购买自己发布的商品")
        self.assertEqual(withdrawn_response.status_code, 400)
        self.assertEqual(withdrawn_response.json()["message"], "该商品不能购买")

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

        buyer_response = self.client.get(
            reverse("api:orders_buyer"),
            **self.auth_headers(self.buyer),
        )
        seller_response = self.client.get(
            reverse("api:orders_seller"),
            **self.auth_headers(self.seller),
        )

        self.assertEqual(buyer_response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in buyer_response.json()["results"]],
            [buyer_order.id],
        )
        self.assertEqual(seller_response.status_code, 200)
        self.assertEqual(
            sorted(item["id"] for item in seller_response.json()["results"]),
            sorted([buyer_order.id, seller_order.id]),
        )

    def test_order_detail_requires_participant_and_exposes_display_fields(self):
        order = self.create_order()

        other_response = self.client.get(
            reverse("api:orders_detail", kwargs={"pk": order.id}),
            **self.auth_headers(self.other),
        )
        buyer_response = self.client.get(
            reverse("api:orders_detail", kwargs={"pk": order.id}),
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(other_response.status_code, 403)
        self.assertEqual(buyer_response.status_code, 200)
        body = buyer_response.json()
        self.assertEqual(body["viewer_role"], "buyer")
        self.assertFalse(body["is_expired"])
        self.assertEqual(body["available_actions"], ["pay"])
        self.assertEqual(body["listing_title_snapshot"], "订单商品")

    def test_expired_order_detail_hides_pay_action(self):
        order = self.create_order(payment_deadline=timezone.now() - timedelta(minutes=1))

        response = self.client.get(
            reverse("api:orders_detail", kwargs={"pk": order.id}),
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_expired"])
        self.assertEqual(response.json()["available_actions"], [])

    def test_buyer_can_pay_and_repeat_or_expired_payment_fail(self):
        order = self.create_order()

        paid_response = self.client.post(
            reverse("api:orders_pay", kwargs={"pk": order.id}),
            **self.auth_headers(self.buyer),
        )
        repeat_response = self.client.post(
            reverse("api:orders_pay", kwargs={"pk": order.id}),
            **self.auth_headers(self.buyer),
        )
        expired_listing = self.create_listing(title="过期支付商品")
        expired_order = self.create_order(
            listing=expired_listing,
            listing_title_snapshot=expired_listing.title,
            payment_deadline=timezone.now() - timedelta(minutes=1),
        )
        expired_response = self.client.post(
            reverse("api:orders_pay", kwargs={"pk": expired_order.id}),
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(paid_response.status_code, 200)
        self.assertEqual(paid_response.json()["status"], Order.OrderStatus.AWAITING_SHIPMENT)
        self.assertEqual(paid_response.json()["available_actions"], [])
        self.assertEqual(repeat_response.status_code, 400)
        self.assertEqual(repeat_response.json()["message"], "该订单已支付或已取消，请勿重复购买")
        self.assertEqual(expired_response.status_code, 400)
        self.assertEqual(expired_response.json()["message"], "订单已超时，系统已自动取消")

    def test_seller_can_confirm_delivery_once(self):
        order = self.create_order(
            status=Order.OrderStatus.AWAITING_SHIPMENT,
            paid_at=timezone.now(),
        )
        self.listing.status = Listing.Status.RESERVED
        self.listing.save(update_fields=["status"])

        response = self.client.post(
            reverse("api:orders_confirm_delivery", kwargs={"pk": order.id}),
            **self.auth_headers(self.seller),
        )
        repeat_response = self.client.post(
            reverse("api:orders_confirm_delivery", kwargs={"pk": order.id}),
            **self.auth_headers(self.seller),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], Order.OrderStatus.AWAITING_RECEIPT)
        self.assertEqual(response.json()["viewer_role"], "seller")
        self.assertEqual(response.json()["available_actions"], [])
        self.assertEqual(repeat_response.status_code, 400)
        self.assertEqual(repeat_response.json()["message"], "订单不是待发货状态")

    def test_wrong_user_cannot_confirm_delivery_or_receipt(self):
        order = self.create_order(
            status=Order.OrderStatus.AWAITING_SHIPMENT,
            paid_at=timezone.now(),
        )
        self.listing.status = Listing.Status.RESERVED
        self.listing.save(update_fields=["status"])

        buyer_delivery_response = self.client.post(
            reverse("api:orders_confirm_delivery", kwargs={"pk": order.id}),
            **self.auth_headers(self.buyer),
        )
        seller_receipt_response = self.client.post(
            reverse("api:orders_confirm_receipt", kwargs={"pk": order.id}),
            **self.auth_headers(self.seller),
        )

        self.assertEqual(buyer_delivery_response.status_code, 403)
        self.assertEqual(seller_receipt_response.status_code, 403)

    def test_buyer_can_confirm_receipt_and_invalid_status_fails(self):
        order = self.create_order(
            status=Order.OrderStatus.AWAITING_RECEIPT,
            paid_at=timezone.now() - timedelta(days=1),
            shipped_at=timezone.now(),
        )
        self.listing.status = Listing.Status.RESERVED
        self.listing.save(update_fields=["status"])
        pending_order = self.create_order()

        response = self.client.post(
            reverse("api:orders_confirm_receipt", kwargs={"pk": order.id}),
            **self.auth_headers(self.buyer),
        )
        invalid_response = self.client.post(
            reverse("api:orders_confirm_receipt", kwargs={"pk": pending_order.id}),
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], Order.OrderStatus.COMPLETED)
        self.assertEqual(response.json()["available_actions"], [])
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.SOLD)
        self.assertEqual(invalid_response.status_code, 400)
        self.assertEqual(invalid_response.json()["message"], "实体商品订单不能确认收货")

    def test_api_does_not_change_celery_task_behavior(self):
        with patch.object(order_tasks, "cancel_expired_pending_orders", return_value=2):
            self.assertEqual(order_tasks.cancel_expired_pending_orders_task(), 2)
        with patch.object(order_tasks, "mark_due_physical_orders_signed", return_value=1):
            self.assertEqual(order_tasks.mark_due_physical_orders_signed_task(), 1)
        with patch.object(order_tasks, "auto_complete_eligible_physical_order", return_value=3), patch.object(
            order_tasks,
            "auto_complete_eligible_virtual_order",
            return_value=4,
        ):
            self.assertEqual(order_tasks.auto_complete_eligible_orders_task(), 7)
