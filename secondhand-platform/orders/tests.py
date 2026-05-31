from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Listing
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

User = get_user_model()


class OrderModelTest(TestCase):
    """Order 模型基础行为测试。"""

    @classmethod
    def setUpTestData(cls):
        cls.buyer = User.objects.create_user(
            username="买家A", email="buyer@test.com", password="testpass123"
        )
        cls.seller = User.objects.create_user(
            username="卖家B", email="seller@test.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="数码产品")
        cls.listing = Listing.objects.create(
            owner=cls.seller,
            category=cls.category,
            title="测试商品",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.ACTIVE,
            price=Decimal("99.00"),
            description="测试描述",
        )

    def test_order_default_status_is_pending_payment(self):
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            listing=self.listing,
            buyer_display_name="买家A",
            seller_display_name="卖家B",
            listing_title_snapshot="测试商品",
            order_price=Decimal("99.00"),
            payment_deadline=timezone.now() + timedelta(minutes=15),
        )
        self.assertEqual(order.status, Order.OrderStatus.PENDING_PAYMENT)

    def test_order_str_representation(self):
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            listing=self.listing,
            buyer_display_name="买家A",
            seller_display_name="卖家B",
            listing_title_snapshot="测试商品",
            order_price=Decimal("99.00"),
            payment_deadline=timezone.now() + timedelta(minutes=15),
        )
        self.assertIn("测试商品", str(order) if hasattr(order, '__str__') else "测试商品")

    def test_order_set_null_on_buyer_delete(self):
        temp_buyer = User.objects.create_user(
            username="临时买家", email="temp@test.com", password="testpass123"
        )
        order = Order.objects.create(
            buyer=temp_buyer,
            seller=self.seller,
            listing=self.listing,
            buyer_display_name="临时买家",
            seller_display_name="卖家B",
            listing_title_snapshot="测试商品",
            order_price=Decimal("99.00"),
            payment_deadline=timezone.now() + timedelta(minutes=15),
        )
        temp_buyer.delete()
        order.refresh_from_db()
        self.assertIsNone(order.buyer)
        self.assertEqual(order.buyer_display_name, "临时买家")


class OrderAdminTest(TestCase):
    """订单后台注册、治理字段和访问烟雾测试。"""

    def test_order_admin_is_registered(self):
        self.assertIsInstance(admin.site._registry[Order], OrderAdmin)

    def test_order_admin_exposes_required_columns_filters_search_and_readonly_fields(self):
        order_admin = admin.site._registry[Order]

        expected_display = [
            "id",
            "buyer",
            "seller",
            "listing",
            "status",
            "order_price",
            "payment_deadline",
            "paid_at",
            "shipped_at",
            "signed_at",
            "completed_at",
            "cancelled_at",
            "created_at",
            "updated_at",
        ]
        for field in expected_display:
            self.assertIn(field, order_admin.list_display)
            self.assertIn(field, order_admin.readonly_fields)
        self.assertIn("logistics_signed_due_at", order_admin.readonly_fields)

        for field in ["status", "buyer", "seller", "created_at", "updated_at"]:
            self.assertIn(field, order_admin.list_filter)

        for field in [
            "listing_title_snapshot",
            "buyer_display_name",
            "seller_display_name",
            "buyer__username",
            "seller__username",
        ]:
            self.assertIn(field, order_admin.search_fields)

        self.assertEqual(order_admin.list_select_related, ["buyer", "seller", "listing"])

    def test_superuser_can_open_order_admin_changelist(self):
        superuser = User.objects.create_superuser(
            username="orderadmin",
            email="orderadmin@example.com",
            password="StrongPass123",
        )
        self.client.force_login(superuser)

        response = self.client.get(reverse("admin:orders_order_changelist"))

        self.assertEqual(response.status_code, 200)

    def test_regular_user_cannot_open_order_admin_changelist(self):
        user = User.objects.create_user(
            username="ordnorm",
            email="ordernormal@example.com",
            password="StrongPass123",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("admin:orders_order_changelist"))

        self.assertIn(response.status_code, [302, 403])


class CreateOrderServiceTest(TestCase):
    """create_order 服务层测试。"""

    @classmethod
    def setUpTestData(cls):
        cls.buyer = User.objects.create_user(
            username="买家A", email="buyer@test.com", password="testpass123"
        )
        cls.seller = User.objects.create_user(
            username="卖家B", email="seller@test.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="数码产品")

    def _create_active_listing(self, **kwargs):
        defaults = {
            "owner": self.seller,
            "category": self.category,
            "title": "测试商品",
            "item_type": Listing.ItemType.PHYSICAL,
            "status": Listing.Status.ACTIVE,
            "price": Decimal("199.00"),
            "description": "测试描述",
        }
        defaults.update(kwargs)
        return Listing.objects.create(**defaults)

    def test_create_order_success(self):
        listing = self._create_active_listing()
        order = create_order(self.buyer, listing)

        self.assertEqual(order.status, Order.OrderStatus.PENDING_PAYMENT)
        self.assertEqual(order.buyer, self.buyer)
        self.assertEqual(order.seller, self.seller)
        self.assertEqual(order.listing, listing)
        self.assertEqual(order.order_price, Decimal("199.00"))
        self.assertEqual(order.listing_title_snapshot, "测试商品")

    def test_create_order_listing_status_unchanged(self):
        listing = self._create_active_listing()
        create_order(self.buyer, listing)

        listing.refresh_from_db()
        self.assertEqual(listing.status, Listing.Status.ACTIVE)

    def test_payment_deadline_is_15_minutes_from_now(self):
        listing = self._create_active_listing()
        before = timezone.now()
        order = create_order(self.buyer, listing)
        after = timezone.now()

        expected_min = before + timedelta(minutes=15)
        expected_max = after + timedelta(minutes=15)
        self.assertGreaterEqual(order.payment_deadline, expected_min)
        self.assertLessEqual(order.payment_deadline, expected_max)

    def test_buyer_cannot_purchase_own_listing(self):
        listing = self._create_active_listing(owner=self.buyer)

        with self.assertRaises(PermissionDenied):
            create_order(self.buyer, listing)

    def test_cannot_order_non_active_listing(self):
        for status in [
            Listing.Status.DRAFT,
            Listing.Status.RESERVED,
            Listing.Status.SOLD,
            Listing.Status.WITHDRAWN,
        ]:
            listing = self._create_active_listing(status=status)
            with self.assertRaises(ValidationError):
                create_order(self.buyer, listing)

    def test_multiple_pending_orders_for_same_listing(self):
        listing = self._create_active_listing()
        another_buyer = User.objects.create_user(
            username="买家C", email="buyerc@test.com", password="testpass123"
        )
        order1 = create_order(self.buyer, listing)
        order2 = create_order(another_buyer, listing)

        self.assertEqual(order1.status, Order.OrderStatus.PENDING_PAYMENT)
        self.assertEqual(order2.status, Order.OrderStatus.PENDING_PAYMENT)
        self.assertEqual(
            Order.objects.filter(
                listing=listing, status=Order.OrderStatus.PENDING_PAYMENT
            ).count(),
            2,
        )

    def test_snapshot_fields_captured_at_creation(self):
        listing = self._create_active_listing(title="原始标题", price=Decimal("50.00"))
        order = create_order(self.buyer, listing)

        listing.title = "修改后标题"
        listing.price = Decimal("999.00")
        listing.save()

        order.refresh_from_db()
        self.assertEqual(order.listing_title_snapshot, "原始标题")
        self.assertEqual(order.order_price, Decimal("50.00"))

    def test_display_name_uses_nickname(self):
        self.buyer.profile.nickname = "买家昵称"
        self.buyer.profile.save()
        self.seller.profile.nickname = "卖家昵称"
        self.seller.profile.save()

        listing = self._create_active_listing()
        order = create_order(self.buyer, listing)

        self.assertEqual(order.buyer_display_name, "买家昵称")
        self.assertEqual(order.seller_display_name, "卖家昵称")


class PurchaseConfirmViewTest(TestCase):
    """购买确认视图测试。"""

    @classmethod
    def setUpTestData(cls):
        cls.buyer = User.objects.create_user(
            username="买家A", email="buyer@test.com", password="testpass123"
        )
        cls.seller = User.objects.create_user(
            username="卖家B", email="seller@test.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="数码产品")
        cls.listing = Listing.objects.create(
            owner=cls.seller,
            category=cls.category,
            title="可购买商品",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.ACTIVE,
            price=Decimal("88.00"),
            description="测试描述",
        )

    def test_guest_redirected_to_login(self):
        url = reverse("catalog:listing_purchase", kwargs={"pk": self.listing.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_get_shows_purchase_confirm_page(self):
        self.client.login(username="买家A", password="testpass123")
        url = reverse("catalog:listing_purchase", kwargs={"pk": self.listing.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "可购买商品")
        self.assertContains(response, "88.00")
        self.assertContains(response, "模拟支付，不会真实扣款")

    def test_post_creates_order_and_redirects(self):
        self.client.login(username="买家A", password="testpass123")
        url = reverse("catalog:listing_purchase", kwargs={"pk": self.listing.pk})
        before_count = Order.objects.count()
        response = self.client.post(url)

        self.assertEqual(Order.objects.count(), before_count + 1)
        order = Order.objects.get(listing=self.listing, buyer=self.buyer)
        self.assertEqual(order.buyer, self.buyer)
        self.assertEqual(order.seller, self.seller)
        self.assertRedirects(
            response,
            reverse("orders:order_detail", kwargs={"pk": order.pk}),
        )

    def test_post_self_purchase_redirects_with_error(self):
        self.client.login(username="卖家B", password="testpass123")
        url = reverse("catalog:listing_purchase", kwargs={"pk": self.listing.pk})
        before_count = Order.objects.count()
        response = self.client.post(url)

        self.assertEqual(Order.objects.count(), before_count)
        self.assertRedirects(
            response,
            reverse("catalog:listing_detail", kwargs={"pk": self.listing.pk}),
        )

    def test_post_non_active_listing_redirects_with_error(self):
        self.client.login(username="买家A", password="testpass123")
        withdrawn_listing = Listing.objects.create(
            owner=self.seller,
            category=self.category,
            title="已下架商品",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.WITHDRAWN,
            price=Decimal("50.00"),
            description="测试",
        )
        url = reverse("catalog:listing_purchase", kwargs={"pk": withdrawn_listing.pk})
        before_count = Order.objects.count()
        response = self.client.post(url)

        self.assertEqual(Order.objects.count(), before_count)
        self.assertRedirects(
            response,
            reverse("catalog:listing_detail", kwargs={"pk": withdrawn_listing.pk}),
            fetch_redirect_response=False,
        )


class OrderDetailViewTest(TestCase):
    """订单详情视图测试。"""

    @classmethod
    def setUpTestData(cls):
        cls.buyer = User.objects.create_user(
            username="买家A", email="buyer@test.com", password="testpass123"
        )
        cls.seller = User.objects.create_user(
            username="卖家B", email="seller@test.com", password="testpass123"
        )
        cls.other_user = User.objects.create_user(
            username="路人C", email="other@test.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="数码产品")
        cls.listing = Listing.objects.create(
            owner=cls.seller,
            category=cls.category,
            title="测试商品",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.ACTIVE,
            price=Decimal("120.00"),
            description="测试描述",
        )
        cls.order = Order.objects.create(
            buyer=cls.buyer,
            seller=cls.seller,
            listing=cls.listing,
            buyer_display_name="买家A",
            seller_display_name="卖家B",
            listing_title_snapshot="测试商品",
            order_price=Decimal("120.00"),
            payment_deadline=timezone.now() + timedelta(minutes=15),
        )

    def test_buyer_can_access_order_detail(self):
        self.client.login(username="买家A", password="testpass123")
        url = reverse("orders:order_detail", kwargs={"pk": self.order.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "测试商品")
        self.assertContains(response, "120.00")

    def test_seller_can_access_order_detail(self):
        self.client.login(username="卖家B", password="testpass123")
        url = reverse("orders:order_detail", kwargs={"pk": self.order.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "测试商品")

    def test_unrelated_user_gets_404(self):
        self.client.login(username="路人C", password="testpass123")
        url = reverse("orders:order_detail", kwargs={"pk": self.order.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_guest_redirected_to_login(self):
        url = reverse("orders:order_detail", kwargs={"pk": self.order.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_nonexistent_order_returns_404(self):
        self.client.login(username="买家A", password="testpass123")
        url = reverse("orders:order_detail", kwargs={"pk": 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_pending_payment_shows_mock_payment_button(self):
        self.client.login(username="买家A", password="testpass123")
        url = reverse("orders:order_detail", kwargs={"pk": self.order.pk})
        response = self.client.get(url)
        self.assertContains(response, "模拟支付")
        self.assertContains(response, "模拟支付，不会真实扣款")

    def test_expired_pending_order_shows_server_side_expiry(self):
        self.order.payment_deadline = timezone.now() - timedelta(minutes=1)
        self.order.save()
        self.client.login(username="买家A", password="testpass123")
        url = reverse("orders:order_detail", kwargs={"pk": self.order.pk})
        response = self.client.get(url)
        self.assertContains(response, "订单已超时")
        self.assertNotContains(response, "确认模拟支付")

    def test_expired_pending_order_tells_seller_not_to_wait_for_payment(self):
        self.order.payment_deadline = timezone.now() - timedelta(minutes=1)
        self.order.save()
        self.client.login(username="卖家B", password="testpass123")
        url = reverse("orders:order_detail", kwargs={"pk": self.order.pk})
        response = self.client.get(url)
        self.assertContains(response, "支付已超时")
        self.assertContains(response, "不需要卖家处理")
        self.assertNotContains(response, "等待买家支付")

    def test_cancelled_order_detail_says_payment_cannot_continue(self):
        self.order.status = Order.OrderStatus.CANCELLED
        self.order.cancelled_at = timezone.now()
        self.order.save()
        self.client.login(username="买家A", password="testpass123")
        url = reverse("orders:order_detail", kwargs={"pk": self.order.pk})
        response = self.client.get(url)
        self.assertContains(response, "该订单已取消，不可继续支付")

    def test_order_detail_has_long_title_wrapping_style(self):
        self.client.login(username="买家A", password="testpass123")
        url = reverse("orders:order_detail", kwargs={"pk": self.order.pk})
        response = self.client.get(url)
        self.assertContains(response, ".order-layout h1")
        self.assertContains(response, "overflow-wrap: anywhere")

    def test_order_detail_shows_snapshot_after_listing_deleted(self):
        temp_listing = Listing.objects.create(
            owner=self.seller,
            category=self.category,
            title="即将删除的商品",
            item_type=Listing.ItemType.VIRTUAL,
            status=Listing.Status.ACTIVE,
            price=Decimal("30.00"),
            description="测试",
        )
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            listing=temp_listing,
            buyer_display_name="买家A",
            seller_display_name="卖家B",
            listing_title_snapshot="即将删除的商品",
            order_price=Decimal("30.00"),
            payment_deadline=timezone.now() + timedelta(minutes=15),
        )
        temp_listing.delete()
        order.refresh_from_db()
        self.assertIsNone(order.listing)

        self.client.login(username="买家A", password="testpass123")
        url = reverse("orders:order_detail", kwargs={"pk": order.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "即将删除的商品")

    def test_buyer_detail_shows_buyer_view_and_back_link(self):
        self.client.login(username="买家A", password="testpass123")
        url = reverse("orders:order_detail", kwargs={"pk": self.order.pk})
        response = self.client.get(url)
        self.assertContains(response, "买家视角")
        self.assertContains(response, reverse("orders:buyer_order_list"))

    def test_seller_detail_shows_seller_view_and_back_link(self):
        self.client.login(username="卖家B", password="testpass123")
        url = reverse("orders:order_detail", kwargs={"pk": self.order.pk})
        response = self.client.get(url)
        self.assertContains(response, "卖家视角")
        self.assertContains(response, reverse("orders:seller_order_list"))

    def test_awaiting_shipment_tells_seller_next_step(self):
        self.order.status = Order.OrderStatus.AWAITING_SHIPMENT
        self.order.paid_at = timezone.now()
        self.order.listing.status = Listing.Status.RESERVED
        self.order.listing.save()
        self.order.save()
        self.client.login(username="卖家B", password="testpass123")
        url = reverse("orders:order_detail", kwargs={"pk": self.order.pk})
        response = self.client.get(url)
        self.assertContains(response, "需要卖家继续处理")
        self.assertContains(response, "确认发货")
        self.assertContains(
            response,
            reverse("orders:confirm_delivery", kwargs={"pk": self.order.pk}),
        )

    def test_virtual_awaiting_shipment_tells_seller_to_confirm_delivery(self):
        virtual_listing = Listing.objects.create(
            owner=self.seller,
            category=self.category,
            title="虚拟资料",
            item_type=Listing.ItemType.VIRTUAL,
            status=Listing.Status.RESERVED,
            price=Decimal("66.00"),
            description="测试描述",
        )
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            listing=virtual_listing,
            buyer_display_name="买家A",
            seller_display_name="卖家B",
            listing_title_snapshot="虚拟资料",
            order_price=Decimal("66.00"),
            status=Order.OrderStatus.AWAITING_SHIPMENT,
            payment_deadline=timezone.now() + timedelta(minutes=15),
            paid_at=timezone.now(),
        )
        self.client.login(username="卖家B", password="testpass123")
        response = self.client.get(reverse("orders:order_detail", kwargs={"pk": order.pk}))
        self.assertContains(response, "确认交付")
        self.assertNotContains(response, "确认发货或交付")

    def test_awaiting_shipment_buyer_cannot_see_confirm_delivery_action(self):
        self.order.status = Order.OrderStatus.AWAITING_SHIPMENT
        self.order.paid_at = timezone.now()
        self.order.save()
        self.client.login(username="买家A", password="testpass123")
        url = reverse("orders:order_detail", kwargs={"pk": self.order.pk})
        response = self.client.get(url)
        self.assertNotContains(response, reverse("orders:confirm_delivery", kwargs={"pk": self.order.pk}))

    def test_awaiting_receipt_tells_seller_waiting_for_buyer(self):
        self.order.status = Order.OrderStatus.AWAITING_RECEIPT
        self.order.shipped_at = timezone.now()
        self.order.save()
        self.client.login(username="卖家B", password="testpass123")
        url = reverse("orders:order_detail", kwargs={"pk": self.order.pk})
        response = self.client.get(url)
        self.assertContains(response, "等待买家确认收货")

    def test_buyer_detail_shows_confirm_receipt_for_awaiting_receipt_order(self):
        self.order.status = Order.OrderStatus.AWAITING_RECEIPT
        self.order.shipped_at = timezone.now()
        self.order.logistics_signed_due_at = timezone.now() + timedelta(days=2)
        self.order.save()
        self.client.login(username="买家A", password="testpass123")
        response = self.client.get(reverse("orders:order_detail", kwargs={"pk": self.order.pk}))
        self.assertContains(response, "确认收货")
        self.assertContains(response, "模拟物流预计签收时间")
        self.assertContains(
            response,
            reverse("orders:order_confirm_receipt", kwargs={"pk": self.order.pk}),
        )

    def test_buyer_detail_shows_confirm_receipt_for_signed_order(self):
        self.order.status = Order.OrderStatus.SIGNED
        self.order.shipped_at = timezone.now() - timedelta(days=2)
        self.order.signed_at = timezone.now()
        self.order.save()
        self.client.login(username="买家A", password="testpass123")
        response = self.client.get(reverse("orders:order_detail", kwargs={"pk": self.order.pk}))
        self.assertContains(response, "已签收")
        self.assertContains(response, "签收后 3 天未确认")
        self.assertContains(response, "确认收货")

    def test_seller_detail_does_not_show_confirm_receipt_form(self):
        self.order.status = Order.OrderStatus.AWAITING_RECEIPT
        self.order.shipped_at = timezone.now()
        self.order.save()
        self.client.login(username="卖家B", password="testpass123")
        response = self.client.get(reverse("orders:order_detail", kwargs={"pk": self.order.pk}))
        self.assertContains(response, "等待买家确认收货")
        self.assertNotContains(response, reverse("orders:order_confirm_receipt", kwargs={"pk": self.order.pk}))

    def test_order_detail_has_no_story_placeholder_copy(self):
        self.order.status = Order.OrderStatus.AWAITING_RECEIPT
        self.order.shipped_at = timezone.now()
        self.order.save()
        self.client.login(username="买家A", password="testpass123")
        response = self.client.get(reverse("orders:order_detail", kwargs={"pk": self.order.pk}))
        self.assertNotContains(response, "Story 5.1")
        self.assertNotContains(response, "Story 5.2")
        self.assertNotContains(response, "后续")


class OrderListViewTest(TestCase):
    """买家和卖家的订单列表视图测试。"""

    @classmethod
    def setUpTestData(cls):
        cls.buyer = User.objects.create_user(
            username="买家A", email="buyer-list@test.com", password="testpass123"
        )
        cls.second_buyer = User.objects.create_user(
            username="买家B", email="buyer2-list@test.com", password="testpass123"
        )
        cls.seller = User.objects.create_user(
            username="卖家A", email="seller-list@test.com", password="testpass123"
        )
        cls.other_seller = User.objects.create_user(
            username="卖家B", email="seller2-list@test.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="订单列表分类")
        cls.seller_listing = Listing.objects.create(
            owner=cls.seller,
            category=cls.category,
            title="卖家A商品",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.ACTIVE,
            price=Decimal("120.00"),
            description="测试描述",
        )
        cls.other_listing = Listing.objects.create(
            owner=cls.other_seller,
            category=cls.category,
            title="其他卖家商品",
            item_type=Listing.ItemType.VIRTUAL,
            status=Listing.Status.ACTIVE,
            price=Decimal("88.00"),
            description="测试描述",
        )
        cls.buyer_order = Order.objects.create(
            buyer=cls.buyer,
            seller=cls.seller,
            listing=cls.seller_listing,
            buyer_display_name="买家A",
            seller_display_name="卖家A",
            listing_title_snapshot="买家订单商品",
            order_price=Decimal("120.00"),
            status=Order.OrderStatus.PENDING_PAYMENT,
            payment_deadline=timezone.now() + timedelta(minutes=15),
        )
        cls.seller_action_order = Order.objects.create(
            buyer=cls.second_buyer,
            seller=cls.seller,
            listing=cls.seller_listing,
            buyer_display_name="买家B",
            seller_display_name="卖家A",
            listing_title_snapshot="卖家待处理商品",
            order_price=Decimal("130.00"),
            status=Order.OrderStatus.AWAITING_SHIPMENT,
            payment_deadline=timezone.now() + timedelta(minutes=15),
            paid_at=timezone.now(),
        )
        cls.other_buyer_order = Order.objects.create(
            buyer=cls.second_buyer,
            seller=cls.other_seller,
            listing=cls.other_listing,
            buyer_display_name="买家B",
            seller_display_name="卖家B",
            listing_title_snapshot="其他买家订单商品",
            order_price=Decimal("88.00"),
            status=Order.OrderStatus.COMPLETED,
            payment_deadline=timezone.now() + timedelta(minutes=15),
            paid_at=timezone.now(),
            completed_at=timezone.now(),
        )

    def test_guest_redirected_from_buyer_order_list(self):
        response = self.client.get(reverse("orders:buyer_order_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_guest_redirected_from_seller_order_list(self):
        response = self.client.get(reverse("orders:seller_order_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_buyer_order_list_url_names(self):
        self.assertEqual(reverse("orders:buyer_order_list"), "/orders/buying/")
        self.assertEqual(reverse("orders:seller_order_list"), "/orders/selling/")

    def test_buyer_order_list_shows_only_current_buyer_orders(self):
        self.client.login(username="买家A", password="testpass123")
        response = self.client.get(reverse("orders:buyer_order_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "买家订单商品")
        self.assertContains(response, "卖家A")
        self.assertContains(response, "120.00")
        self.assertContains(response, "待支付")
        self.assertContains(response, "支付截止")
        self.assertNotContains(response, "卖家待处理商品")
        self.assertNotContains(response, "其他买家订单商品")

    def test_buyer_order_list_marks_expired_pending_order_unpayable(self):
        self.buyer_order.payment_deadline = timezone.now() - timedelta(minutes=1)
        self.buyer_order.save()
        self.client.login(username="买家A", password="testpass123")
        response = self.client.get(reverse("orders:buyer_order_list"))
        self.assertContains(response, "订单已超时，不可继续支付")
        self.assertNotContains(response, "在订单详情页完成模拟支付")

    def test_seller_order_list_shows_only_current_seller_orders(self):
        self.client.login(username="卖家A", password="testpass123")
        response = self.client.get(reverse("orders:seller_order_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "买家订单商品")
        self.assertContains(response, "卖家待处理商品")
        self.assertContains(response, "需要卖家继续处理")
        self.assertContains(response, "进入详情页确认发货或交付")
        self.assertContains(response, "买家B")
        self.assertNotContains(response, "其他买家订单商品")
        self.assertNotContains(response, "Story 5.1")

    def test_seller_order_list_marks_expired_pending_order_as_no_action_needed(self):
        self.buyer_order.payment_deadline = timezone.now() - timedelta(minutes=1)
        self.buyer_order.save()
        self.client.login(username="卖家A", password="testpass123")
        response = self.client.get(reverse("orders:seller_order_list"))
        self.assertContains(response, "支付已超时，等待系统取消")
        self.assertContains(response, "不需要卖家处理")

    def test_order_lists_link_to_order_detail(self):
        self.client.login(username="买家A", password="testpass123")
        response = self.client.get(reverse("orders:buyer_order_list"))
        detail_url = reverse("orders:order_detail", kwargs={"pk": self.buyer_order.pk})
        self.assertContains(response, detail_url)

    def test_order_list_shows_snapshot_after_listing_deleted(self):
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.other_seller,
            listing=self.other_listing,
            buyer_display_name="买家A",
            seller_display_name="卖家B",
            listing_title_snapshot="快照商品标题",
            order_price=Decimal("66.00"),
            status=Order.OrderStatus.CANCELLED,
            payment_deadline=timezone.now() + timedelta(minutes=15),
            cancelled_at=timezone.now(),
        )
        self.other_listing.delete()
        order.refresh_from_db()
        self.assertIsNone(order.listing)

        self.client.login(username="买家A", password="testpass123")
        response = self.client.get(reverse("orders:buyer_order_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "快照商品标题")
        self.assertContains(response, "66.00")
        self.assertContains(response, "已取消")

    def test_nav_contains_order_list_links_for_authenticated_user(self):
        self.client.login(username="买家A", password="testpass123")
        response = self.client.get(reverse("catalog:listing_list"))
        self.assertContains(response, reverse("orders:buyer_order_list"))
        self.assertContains(response, reverse("orders:seller_order_list"))

    def test_selectors_return_none_for_anonymous_user(self):
        anonymous = AnonymousUser()
        self.assertEqual(get_buyer_orders(anonymous).count(), 0)
        self.assertEqual(get_seller_orders(anonymous).count(), 0)

    def test_buyer_order_list_shows_awaiting_receipt_guidance(self):
        self.buyer_order.status = Order.OrderStatus.AWAITING_RECEIPT
        self.buyer_order.shipped_at = timezone.now()
        self.buyer_order.logistics_signed_due_at = timezone.now() + timedelta(days=2)
        self.buyer_order.save()
        self.client.login(username="买家A", password="testpass123")
        response = self.client.get(reverse("orders:buyer_order_list"))
        self.assertContains(response, "运输中，等待模拟物流签收")
        self.assertNotContains(response, "Story 5.2")

    def test_buyer_order_list_shows_signed_guidance(self):
        self.buyer_order.status = Order.OrderStatus.SIGNED
        self.buyer_order.shipped_at = timezone.now() - timedelta(days=2)
        self.buyer_order.signed_at = timezone.now()
        self.buyer_order.save()
        self.client.login(username="买家A", password="testpass123")
        response = self.client.get(reverse("orders:buyer_order_list"))
        self.assertContains(response, "已签收，进入详情页确认收货")
        self.assertContains(response, "签收后 3 天将自动确认")

    def test_seller_order_list_shows_awaiting_receipt_guidance(self):
        self.seller_action_order.status = Order.OrderStatus.AWAITING_RECEIPT
        self.seller_action_order.shipped_at = timezone.now()
        self.seller_action_order.logistics_signed_due_at = timezone.now() + timedelta(days=2)
        self.seller_action_order.save()
        self.client.login(username="卖家A", password="testpass123")
        response = self.client.get(reverse("orders:seller_order_list"))
        self.assertContains(response, "已发货，运输中")
        self.assertContains(response, "等待模拟物流签收")
        self.assertNotContains(response, "Story 5.2")

    def test_order_lists_have_no_story_placeholder_copy(self):
        self.client.login(username="买家A", password="testpass123")
        buyer_response = self.client.get(reverse("orders:buyer_order_list"))
        self.assertNotContains(buyer_response, "Story 5.1")
        self.assertNotContains(buyer_response, "Story 5.2")
        self.client.logout()

        self.client.login(username="卖家A", password="testpass123")
        seller_response = self.client.get(reverse("orders:seller_order_list"))
        self.assertNotContains(seller_response, "Story 5.1")
        self.assertNotContains(seller_response, "Story 5.2")


class PayOrderServiceTest(TransactionTestCase):
    """pay_order 服务层测试。使用 TransactionTestCase 以正确测试 select_for_update 行为。"""

    def setUp(self):
        self.buyer = User.objects.create_user(
            username="买家A", email="buyer@test.com", password="testpass123"
        )
        self.seller = User.objects.create_user(
            username="卖家B", email="seller@test.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="路人C", email="other@test.com", password="testpass123"
        )
        self.category = Category.objects.create(name="数码产品")
        self.listing = Listing.objects.create(
            owner=self.seller,
            category=self.category,
            title="测试商品",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.ACTIVE,
            price=Decimal("99.00"),
            description="测试描述",
        )

    def _create_pending_order(self, buyer=None, listing=None, deadline_minutes=15):
        buyer = buyer or self.buyer
        listing = listing or self.listing
        return Order.objects.create(
            buyer=buyer,
            seller=self.seller,
            listing=listing,
            buyer_display_name=buyer.username,
            seller_display_name=self.seller.username,
            listing_title_snapshot=listing.title,
            order_price=listing.price,
            status=Order.OrderStatus.PENDING_PAYMENT,
            payment_deadline=timezone.now() + timedelta(minutes=deadline_minutes),
        )

    def test_buyer_can_pay_pending_order(self):
        order = self._create_pending_order()
        pay_order(self.buyer, order.pk)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_SHIPMENT)
        self.assertIsNotNone(order.paid_at)

    def test_payment_sets_listing_to_reserved(self):
        order = self._create_pending_order()
        pay_order(self.buyer, order.pk)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.RESERVED)

    def test_payment_does_not_set_completed(self):
        order = self._create_pending_order()
        pay_order(self.buyer, order.pk)
        order.refresh_from_db()
        self.assertNotEqual(order.status, Order.OrderStatus.COMPLETED)
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_SHIPMENT)

    def test_seller_cannot_pay(self):
        order = self._create_pending_order()
        with self.assertRaises(PermissionDenied):
            pay_order(self.seller, order.pk)

    def test_other_user_cannot_pay(self):
        order = self._create_pending_order()
        with self.assertRaises(PermissionDenied):
            pay_order(self.other_user, order.pk)

    def test_expired_order_payment_fails_and_cancels(self):
        order = self._create_pending_order(deadline_minutes=-1)
        with self.assertRaises(ValidationError) as ctx:
            pay_order(self.buyer, order.pk)
        self.assertIn("超时", str(ctx.exception.message))

    def test_non_active_listing_payment_fails(self):
        self.listing.status = Listing.Status.RESERVED
        self.listing.save()
        order = self._create_pending_order()
        with self.assertRaises(ValidationError) as ctx:
            pay_order(self.buyer, order.pk)
        self.assertIn("不可购买", str(ctx.exception.message))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.PENDING_PAYMENT)

    def test_concurrent_orders_only_one_succeeds(self):
        buyer2 = User.objects.create_user(
            username="买家D", email="buyerd@test.com", password="testpass123"
        )
        order1 = self._create_pending_order(buyer=self.buyer)
        order2 = self._create_pending_order(buyer=buyer2)

        pay_order(self.buyer, order1.pk)

        with self.assertRaises(ValidationError):
            pay_order(buyer2, order2.pk)

        order1.refresh_from_db()
        order2.refresh_from_db()
        self.listing.refresh_from_db()
        self.assertEqual(order1.status, Order.OrderStatus.AWAITING_SHIPMENT)
        self.assertNotEqual(order2.status, Order.OrderStatus.AWAITING_SHIPMENT)
        self.assertEqual(self.listing.status, Listing.Status.RESERVED)

    def test_listing_none_payment_fails(self):
        order = self._create_pending_order()
        order.listing = None
        order.save()
        with self.assertRaises(ValidationError) as ctx:
            pay_order(self.buyer, order.pk)
        self.assertIn("商品不存在", str(ctx.exception.message))

    def test_already_paid_order_cannot_pay_again(self):
        order = self._create_pending_order()
        pay_order(self.buyer, order.pk)
        with self.assertRaises(ValidationError):
            pay_order(self.buyer, order.pk)


class ConfirmOrderDeliveryServiceTest(TransactionTestCase):
    """confirm_order_delivery 服务层测试。"""

    def setUp(self):
        self.buyer = User.objects.create_user(
            username="交付买家", email="delivery-buyer@test.com", password="testpass123"
        )
        self.seller = User.objects.create_user(
            username="交付卖家", email="delivery-seller@test.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="交付路人", email="delivery-other@test.com", password="testpass123"
        )
        self.category = Category.objects.create(name="交付分类")

    def _create_listing(self, item_type=Listing.ItemType.PHYSICAL, status=Listing.Status.RESERVED):
        return Listing.objects.create(
            owner=self.seller,
            category=self.category,
            title="交付商品",
            item_type=item_type,
            status=status,
            price=Decimal("99.00"),
            description="测试描述",
        )

    def _create_order(self, status=Order.OrderStatus.AWAITING_SHIPMENT, listing=None):
        listing = listing or self._create_listing()
        return Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            listing=listing,
            buyer_display_name=self.buyer.username,
            seller_display_name=self.seller.username,
            listing_title_snapshot=listing.title,
            order_price=listing.price,
            status=status,
            payment_deadline=timezone.now() + timedelta(minutes=15),
            paid_at=timezone.now(),
        )

    def test_seller_can_confirm_physical_delivery(self):
        order = self._create_order()
        before = timezone.now()
        confirm_order_delivery(self.seller, order.pk)
        after = timezone.now()
        order.refresh_from_db()
        order.listing.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_RECEIPT)
        self.assertIsNotNone(order.shipped_at)
        self.assertEqual(order.listing.status, Listing.Status.RESERVED)
        self.assertIsNotNone(order.logistics_signed_due_at)
        self.assertGreaterEqual(order.logistics_signed_due_at, order.shipped_at + timedelta(days=1))
        self.assertLessEqual(order.logistics_signed_due_at, order.shipped_at + timedelta(days=5))
        self.assertGreaterEqual(order.shipped_at, before)

    def test_virtual_delivery_does_not_create_logistics_due_at(self):
        listing = self._create_listing(item_type=Listing.ItemType.VIRTUAL)
        order = self._create_order(listing=listing)
        confirm_order_delivery(self.seller, order.pk)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_RECEIPT)
        self.assertIsNotNone(order.shipped_at)
        self.assertIsNone(order.logistics_signed_due_at)

    def test_buyer_and_other_user_cannot_confirm_delivery(self):
        for user in [self.buyer, self.other_user]:
            order = self._create_order()
            with self.assertRaises(PermissionDenied):
                confirm_order_delivery(user, order.pk)
            order.refresh_from_db()
            self.assertEqual(order.status, Order.OrderStatus.AWAITING_SHIPMENT)
            self.assertIsNone(order.shipped_at)

    def test_invalid_statuses_cannot_confirm_delivery(self):
        invalid_statuses = [
            Order.OrderStatus.PENDING_PAYMENT,
            Order.OrderStatus.CANCELLED,
            Order.OrderStatus.AWAITING_RECEIPT,
            Order.OrderStatus.SIGNED,
            Order.OrderStatus.COMPLETED,
        ]
        for status in invalid_statuses:
            order = self._create_order(status=status)
            with self.assertRaises(ValidationError):
                confirm_order_delivery(self.seller, order.pk)
            order.refresh_from_db()
            self.assertEqual(order.status, status)
            self.assertIsNone(order.shipped_at)
            self.assertIsNone(order.logistics_signed_due_at)

    def test_listing_none_cannot_confirm_delivery(self):
        order = self._create_order()
        order.listing = None
        order.save(update_fields=["listing"])
        with self.assertRaises(ValidationError):
            confirm_order_delivery(self.seller, order.pk)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_SHIPMENT)
        self.assertIsNone(order.shipped_at)

    def test_non_reserved_listing_cannot_confirm_delivery(self):
        listing = self._create_listing(status=Listing.Status.ACTIVE)
        order = self._create_order(listing=listing)
        with self.assertRaises(ValidationError):
            confirm_order_delivery(self.seller, order.pk)
        order.refresh_from_db()
        listing.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_SHIPMENT)
        self.assertEqual(listing.status, Listing.Status.ACTIVE)

    def test_repeated_delivery_confirmation_is_idempotently_rejected(self):
        order = self._create_order()
        confirm_order_delivery(self.seller, order.pk)
        order.refresh_from_db()
        shipped_at = order.shipped_at
        logistics_signed_due_at = order.logistics_signed_due_at
        with self.assertRaises(ValidationError):
            confirm_order_delivery(self.seller, order.pk)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_RECEIPT)
        self.assertEqual(order.shipped_at, shipped_at)
        self.assertEqual(order.logistics_signed_due_at, logistics_signed_due_at)


class ConfirmOrderReceiptServiceTest(TransactionTestCase):
    """confirm_order_receipt 服务层测试。"""

    def setUp(self):
        self.buyer = User.objects.create_user(
            username="收货买家", email="receipt-buyer@test.com", password="testpass123"
        )
        self.seller = User.objects.create_user(
            username="收货卖家", email="receipt-seller@test.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="收货路人", email="receipt-other@test.com", password="testpass123"
        )
        self.category = Category.objects.create(name="收货分类")

    def _create_listing(self, item_type=Listing.ItemType.PHYSICAL, status=Listing.Status.RESERVED):
        return Listing.objects.create(
            owner=self.seller,
            category=self.category,
            title="收货商品",
            item_type=item_type,
            status=status,
            price=Decimal("109.00"),
            description="测试描述",
        )

    def _create_order(self, status=Order.OrderStatus.AWAITING_RECEIPT, listing=None, **kwargs):
        listing = listing or self._create_listing()
        defaults = {
            "buyer": self.buyer,
            "seller": self.seller,
            "listing": listing,
            "buyer_display_name": self.buyer.username,
            "seller_display_name": self.seller.username,
            "listing_title_snapshot": listing.title,
            "order_price": listing.price,
            "status": status,
            "payment_deadline": timezone.now() + timedelta(minutes=15),
            "paid_at": timezone.now() - timedelta(days=1),
            "shipped_at": timezone.now() - timedelta(hours=2),
        }
        defaults.update(kwargs)
        return Order.objects.create(**defaults)

    def test_buyer_can_complete_virtual_awaiting_receipt_order(self):
        listing = self._create_listing(item_type=Listing.ItemType.VIRTUAL)
        order = self._create_order(listing=listing)
        confirm_order_receipt(self.buyer, order.pk)
        order.refresh_from_db()
        listing.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.COMPLETED)
        self.assertIsNotNone(order.completed_at)
        self.assertEqual(listing.status, Listing.Status.SOLD)

    def test_buyer_can_complete_physical_awaiting_receipt_order(self):
        order = self._create_order(status=Order.OrderStatus.AWAITING_RECEIPT)
        confirm_order_receipt(self.buyer, order.pk)
        order.refresh_from_db()
        order.listing.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.COMPLETED)
        self.assertIsNotNone(order.completed_at)
        self.assertEqual(order.listing.status, Listing.Status.SOLD)

    def test_buyer_can_complete_physical_signed_order(self):
        order = self._create_order(status=Order.OrderStatus.SIGNED, signed_at=timezone.now())
        confirm_order_receipt(self.buyer, order.pk)
        order.refresh_from_db()
        order.listing.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.COMPLETED)
        self.assertIsNotNone(order.completed_at)
        self.assertEqual(order.listing.status, Listing.Status.SOLD)

    def test_seller_and_other_user_cannot_confirm_receipt(self):
        for user in [self.seller, self.other_user]:
            order = self._create_order()
            with self.assertRaises(PermissionDenied):
                confirm_order_receipt(user, order.pk)
            order.refresh_from_db()
            self.assertEqual(order.status, Order.OrderStatus.AWAITING_RECEIPT)
            self.assertIsNone(order.completed_at)

    def test_invalid_statuses_cannot_confirm_receipt(self):
        for status in [
            Order.OrderStatus.PENDING_PAYMENT,
            Order.OrderStatus.CANCELLED,
            Order.OrderStatus.AWAITING_SHIPMENT,
            Order.OrderStatus.COMPLETED,
        ]:
            order = self._create_order(status=status)
            with self.assertRaises(ValidationError):
                confirm_order_receipt(self.buyer, order.pk)
            order.refresh_from_db()
            self.assertEqual(order.status, status)
            self.assertIsNone(order.completed_at)

    def test_listing_none_cannot_confirm_receipt(self):
        order = self._create_order()
        order.listing = None
        order.save(update_fields=["listing"])
        with self.assertRaises(ValidationError):
            confirm_order_receipt(self.buyer, order.pk)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_RECEIPT)
        self.assertIsNone(order.completed_at)

    def test_non_reserved_listing_cannot_confirm_receipt(self):
        listing = self._create_listing(status=Listing.Status.ACTIVE)
        order = self._create_order(listing=listing)
        with self.assertRaises(ValidationError):
            confirm_order_receipt(self.buyer, order.pk)
        order.refresh_from_db()
        listing.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_RECEIPT)
        self.assertEqual(listing.status, Listing.Status.ACTIVE)

    def test_repeated_receipt_confirmation_does_not_override_completed_at(self):
        listing = self._create_listing(item_type=Listing.ItemType.VIRTUAL)
        order = self._create_order(listing=listing)
        confirm_order_receipt(self.buyer, order.pk)
        order.refresh_from_db()
        completed_at = order.completed_at
        with self.assertRaises(ValidationError):
            confirm_order_receipt(self.buyer, order.pk)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.COMPLETED)
        self.assertEqual(order.completed_at, completed_at)


class DeliveryAndReceiptTaskServiceTest(TransactionTestCase):
    """模拟签收和自动完成服务测试。"""

    def setUp(self):
        self.buyer = User.objects.create_user(
            username="任务买家", email="task-buyer@test.com", password="testpass123"
        )
        self.seller = User.objects.create_user(
            username="任务卖家", email="task-seller@test.com", password="testpass123"
        )
        self.category = Category.objects.create(name="任务分类")

    def _create_listing(self, item_type=Listing.ItemType.PHYSICAL, status=Listing.Status.RESERVED):
        return Listing.objects.create(
            owner=self.seller,
            category=self.category,
            title="任务商品",
            item_type=item_type,
            status=status,
            price=Decimal("119.00"),
            description="测试描述",
        )

    def _create_order(self, listing=None, status=Order.OrderStatus.AWAITING_RECEIPT, **kwargs):
        listing = listing or self._create_listing()
        defaults = {
            "buyer": self.buyer,
            "seller": self.seller,
            "listing": listing,
            "buyer_display_name": self.buyer.username,
            "seller_display_name": self.seller.username,
            "listing_title_snapshot": listing.title,
            "order_price": listing.price,
            "status": status,
            "payment_deadline": timezone.now() + timedelta(minutes=15),
            "paid_at": timezone.now() - timedelta(days=2),
            "shipped_at": timezone.now() - timedelta(days=2),
        }
        defaults.update(kwargs)
        return Order.objects.create(**defaults)

    def test_mark_due_physical_orders_signed_only_updates_due_physical_orders(self):
        now = timezone.now()
        due = self._create_order(logistics_signed_due_at=now - timedelta(minutes=1))
        not_due = self._create_order(logistics_signed_due_at=now + timedelta(days=1))
        virtual = self._create_order(
            listing=self._create_listing(item_type=Listing.ItemType.VIRTUAL),
            logistics_signed_due_at=now - timedelta(minutes=1),
        )
        count = mark_due_physical_orders_signed(now=now)
        self.assertEqual(count, 1)
        due.refresh_from_db()
        not_due.refresh_from_db()
        virtual.refresh_from_db()
        self.assertEqual(due.status, Order.OrderStatus.SIGNED)
        self.assertIsNotNone(due.signed_at)
        self.assertEqual(not_due.status, Order.OrderStatus.AWAITING_RECEIPT)
        self.assertEqual(virtual.status, Order.OrderStatus.AWAITING_RECEIPT)
        due.listing.refresh_from_db()
        self.assertEqual(due.listing.status, Listing.Status.RESERVED)

    def test_mark_due_physical_orders_signed_is_idempotent(self):
        now = timezone.now()
        order = self._create_order(logistics_signed_due_at=now - timedelta(minutes=1))
        first = mark_due_physical_orders_signed(now=now)
        order.refresh_from_db()
        signed_at = order.signed_at
        second = mark_due_physical_orders_signed(now=now + timedelta(minutes=5))
        order.refresh_from_db()
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        self.assertEqual(order.signed_at, signed_at)

    def test_auto_complete_physical_signed_after_three_days(self):
        now = timezone.now()
        order = self._create_order(
            status=Order.OrderStatus.SIGNED,
            signed_at=now - timedelta(days=3, minutes=1),
        )
        count = auto_complete_eligible_physical_order(now=now)
        order.refresh_from_db()
        order.listing.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(order.status, Order.OrderStatus.COMPLETED)
        self.assertIsNotNone(order.completed_at)
        self.assertEqual(order.listing.status, Listing.Status.SOLD)

    def test_auto_complete_physical_not_before_three_days(self):
        now = timezone.now()
        order = self._create_order(
            status=Order.OrderStatus.SIGNED,
            signed_at=now - timedelta(days=2, hours=23),
        )
        count = auto_complete_eligible_physical_order(now=now)
        order.refresh_from_db()
        self.assertEqual(count, 0)
        self.assertEqual(order.status, Order.OrderStatus.SIGNED)

    def test_auto_complete_virtual_after_seven_days(self):
        now = timezone.now()
        listing = self._create_listing(item_type=Listing.ItemType.VIRTUAL)
        order = self._create_order(
            listing=listing,
            shipped_at=now - timedelta(days=7, minutes=1),
        )
        count = auto_complete_eligible_virtual_order(now=now)
        order.refresh_from_db()
        listing.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(order.status, Order.OrderStatus.COMPLETED)
        self.assertIsNotNone(order.completed_at)
        self.assertEqual(listing.status, Listing.Status.SOLD)

    def test_auto_complete_virtual_not_before_seven_days(self):
        now = timezone.now()
        listing = self._create_listing(item_type=Listing.ItemType.VIRTUAL)
        order = self._create_order(
            listing=listing,
            shipped_at=now - timedelta(days=6, hours=23),
        )
        count = auto_complete_eligible_virtual_order(now=now)
        order.refresh_from_db()
        self.assertEqual(count, 0)
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_RECEIPT)

    def test_auto_complete_is_idempotent(self):
        now = timezone.now()
        order = self._create_order(
            status=Order.OrderStatus.SIGNED,
            signed_at=now - timedelta(days=3, minutes=1),
        )
        first = auto_complete_eligible_physical_order(now=now)
        order.refresh_from_db()
        completed_at = order.completed_at
        second = auto_complete_eligible_physical_order(now=now + timedelta(minutes=5))
        order.refresh_from_db()
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        self.assertEqual(order.completed_at, completed_at)

    def test_tasks_return_processed_counts(self):
        with patch.object(order_tasks, "mark_due_physical_orders_signed", return_value=2):
            self.assertEqual(order_tasks.mark_due_physical_orders_signed_task(), 2)
        with patch.object(order_tasks, "auto_complete_eligible_physical_order", return_value=1), patch.object(
            order_tasks, "auto_complete_eligible_virtual_order", return_value=3
        ):
            self.assertEqual(order_tasks.auto_complete_eligible_orders_task(), 4)


class CancelExpiredOrdersTest(TestCase):
    """cancel_expired_pending_orders 服务层测试。"""

    @classmethod
    def setUpTestData(cls):
        cls.buyer = User.objects.create_user(
            username="买家A", email="buyer@test.com", password="testpass123"
        )
        cls.seller = User.objects.create_user(
            username="卖家B", email="seller@test.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="数码产品")
        cls.listing = Listing.objects.create(
            owner=cls.seller,
            category=cls.category,
            title="测试商品",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.ACTIVE,
            price=Decimal("99.00"),
            description="测试描述",
        )

    def _create_order(self, status, deadline_minutes):
        return Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            listing=self.listing,
            buyer_display_name="买家A",
            seller_display_name="卖家B",
            listing_title_snapshot="测试商品",
            order_price=Decimal("99.00"),
            status=status,
            payment_deadline=timezone.now() + timedelta(minutes=deadline_minutes),
        )

    def test_cancels_expired_pending_orders(self):
        order = self._create_order(Order.OrderStatus.PENDING_PAYMENT, -5)
        count = cancel_expired_pending_orders()
        self.assertEqual(count, 1)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.CANCELLED)
        self.assertIsNotNone(order.cancelled_at)

    def test_does_not_cancel_non_expired_orders(self):
        order = self._create_order(Order.OrderStatus.PENDING_PAYMENT, 10)
        count = cancel_expired_pending_orders()
        self.assertEqual(count, 0)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.PENDING_PAYMENT)

    def test_does_not_modify_paid_orders(self):
        order = self._create_order(Order.OrderStatus.AWAITING_SHIPMENT, -5)
        count = cancel_expired_pending_orders()
        self.assertEqual(count, 0)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_SHIPMENT)

    def test_does_not_modify_already_cancelled_orders(self):
        order = self._create_order(Order.OrderStatus.CANCELLED, -5)
        count = cancel_expired_pending_orders()
        self.assertEqual(count, 0)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.CANCELLED)

    def test_idempotent_repeated_execution(self):
        self._create_order(Order.OrderStatus.PENDING_PAYMENT, -5)
        count1 = cancel_expired_pending_orders()
        count2 = cancel_expired_pending_orders()
        self.assertEqual(count1, 1)
        self.assertEqual(count2, 0)

    def test_does_not_modify_listing_status(self):
        self._create_order(Order.OrderStatus.PENDING_PAYMENT, -5)
        cancel_expired_pending_orders()
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.ACTIVE)


class OrderPayViewTest(TestCase):
    """OrderPayView 视图层测试。"""

    @classmethod
    def setUpTestData(cls):
        cls.buyer = User.objects.create_user(
            username="买家A", email="buyer@test.com", password="testpass123"
        )
        cls.seller = User.objects.create_user(
            username="卖家B", email="seller@test.com", password="testpass123"
        )
        cls.other_user = User.objects.create_user(
            username="路人C", email="other@test.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="数码产品")
        cls.listing = Listing.objects.create(
            owner=cls.seller,
            category=cls.category,
            title="测试商品",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.ACTIVE,
            price=Decimal("99.00"),
            description="测试描述",
        )

    def _create_pending_order(self):
        return Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            listing=self.listing,
            buyer_display_name="买家A",
            seller_display_name="卖家B",
            listing_title_snapshot="测试商品",
            order_price=Decimal("99.00"),
            status=Order.OrderStatus.PENDING_PAYMENT,
            payment_deadline=timezone.now() + timedelta(minutes=15),
        )

    def test_get_not_allowed(self):
        self.client.login(username="买家A", password="testpass123")
        order = self._create_pending_order()
        url = reverse("orders:order_pay", kwargs={"pk": order.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_guest_redirected_to_login(self):
        order = self._create_pending_order()
        url = reverse("orders:order_pay", kwargs={"pk": order.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_buyer_can_pay_via_post(self):
        self.client.login(username="买家A", password="testpass123")
        order = self._create_pending_order()
        url = reverse("orders:order_pay", kwargs={"pk": order.pk})
        response = self.client.post(url)
        self.assertRedirects(
            response,
            reverse("orders:order_detail", kwargs={"pk": order.pk}),
            fetch_redirect_response=False,
        )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_SHIPMENT)

    def test_seller_cannot_pay(self):
        self.client.login(username="卖家B", password="testpass123")
        order = self._create_pending_order()
        url = reverse("orders:order_pay", kwargs={"pk": order.pk})
        response = self.client.post(url)
        self.assertRedirects(
            response,
            reverse("orders:order_detail", kwargs={"pk": order.pk}),
            fetch_redirect_response=False,
        )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.PENDING_PAYMENT)

    def test_other_user_cannot_pay(self):
        self.client.login(username="路人C", password="testpass123")
        order = self._create_pending_order()
        url = reverse("orders:order_pay", kwargs={"pk": order.pk})
        response = self.client.post(url)
        self.assertRedirects(
            response,
            reverse("orders:order_detail", kwargs={"pk": order.pk}),
            fetch_redirect_response=False,
        )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.PENDING_PAYMENT)

    def test_expired_order_shows_error_message(self):
        self.client.login(username="买家A", password="testpass123")
        order = self._create_pending_order()
        order.payment_deadline = timezone.now() - timedelta(minutes=1)
        order.save()
        url = reverse("orders:order_pay", kwargs={"pk": order.pk})
        response = self.client.post(url, follow=True)
        self.assertContains(response, "超时")

    def test_success_shows_success_message(self):
        self.client.login(username="买家A", password="testpass123")
        order = self._create_pending_order()
        url = reverse("orders:order_pay", kwargs={"pk": order.pk})
        response = self.client.post(url, follow=True)
        self.assertContains(response, "完成支付")

    def test_nonexistent_order_returns_404(self):
        self.client.login(username="买家A", password="testpass123")
        url = reverse("orders:order_pay", kwargs={"pk": 99999})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)


class OrderConfirmDeliveryViewTest(TestCase):
    """卖家确认交付视图测试。"""

    @classmethod
    def setUpTestData(cls):
        cls.buyer = User.objects.create_user(
            username="交付视图买家", email="delivery-view-buyer@test.com", password="testpass123"
        )
        cls.seller = User.objects.create_user(
            username="交付视图卖家", email="delivery-view-seller@test.com", password="testpass123"
        )
        cls.other_user = User.objects.create_user(
            username="交付视图路人", email="delivery-view-other@test.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="交付视图分类")

    def _create_order(self):
        listing = Listing.objects.create(
            owner=self.seller,
            category=self.category,
            title="交付视图商品",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.RESERVED,
            price=Decimal("99.00"),
            description="测试描述",
        )
        return Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            listing=listing,
            buyer_display_name=self.buyer.username,
            seller_display_name=self.seller.username,
            listing_title_snapshot=listing.title,
            order_price=listing.price,
            status=Order.OrderStatus.AWAITING_SHIPMENT,
            payment_deadline=timezone.now() + timedelta(minutes=15),
            paid_at=timezone.now(),
        )

    def test_get_not_allowed(self):
        order = self._create_order()
        self.client.login(username="交付视图卖家", password="testpass123")
        response = self.client.get(reverse("orders:confirm_delivery", kwargs={"pk": order.pk}))
        self.assertEqual(response.status_code, 405)

    def test_guest_redirected_to_login(self):
        order = self._create_order()
        response = self.client.post(reverse("orders:confirm_delivery", kwargs={"pk": order.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_seller_can_confirm_delivery_via_post(self):
        order = self._create_order()
        self.client.login(username="交付视图卖家", password="testpass123")
        response = self.client.post(reverse("orders:confirm_delivery", kwargs={"pk": order.pk}), follow=True)
        order.refresh_from_db()
        self.assertRedirects(
            response,
            reverse("orders:order_detail", kwargs={"pk": order.pk}),
            fetch_redirect_response=False,
        )
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_RECEIPT)
        self.assertContains(response, "已确认发货")

    def test_buyer_or_other_user_cannot_confirm_delivery(self):
        for username in ["交付视图买家", "交付视图路人"]:
            order = self._create_order()
            self.client.login(username=username, password="testpass123")
            response = self.client.post(reverse("orders:confirm_delivery", kwargs={"pk": order.pk}))
            order.refresh_from_db()
            self.assertIn(response.status_code, [302, 404])
            self.assertEqual(order.status, Order.OrderStatus.AWAITING_SHIPMENT)
            self.client.logout()


class OrderConfirmReceiptViewTest(TestCase):
    """买家确认收货视图测试。"""

    @classmethod
    def setUpTestData(cls):
        cls.buyer = User.objects.create_user(
            username="收货视图买家", email="receipt-view-buyer@test.com", password="testpass123"
        )
        cls.seller = User.objects.create_user(
            username="收货视图卖家", email="receipt-view-seller@test.com", password="testpass123"
        )
        cls.other_user = User.objects.create_user(
            username="收货视图路人", email="receipt-view-other@test.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="收货视图分类")

    def _create_order(self, item_type=Listing.ItemType.VIRTUAL):
        listing = Listing.objects.create(
            owner=self.seller,
            category=self.category,
            title="收货视图商品",
            item_type=item_type,
            status=Listing.Status.RESERVED,
            price=Decimal("99.00"),
            description="测试描述",
        )
        return Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            listing=listing,
            buyer_display_name=self.buyer.username,
            seller_display_name=self.seller.username,
            listing_title_snapshot=listing.title,
            order_price=listing.price,
            status=Order.OrderStatus.AWAITING_RECEIPT,
            payment_deadline=timezone.now() + timedelta(minutes=15),
            paid_at=timezone.now() - timedelta(days=1),
            shipped_at=timezone.now(),
        )

    def test_get_not_allowed(self):
        order = self._create_order()
        self.client.login(username="收货视图买家", password="testpass123")
        response = self.client.get(reverse("orders:order_confirm_receipt", kwargs={"pk": order.pk}))
        self.assertEqual(response.status_code, 405)

    def test_guest_redirected_to_login(self):
        order = self._create_order()
        response = self.client.post(reverse("orders:order_confirm_receipt", kwargs={"pk": order.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_buyer_can_confirm_receipt_via_post(self):
        order = self._create_order()
        self.client.login(username="收货视图买家", password="testpass123")
        response = self.client.post(
            reverse("orders:order_confirm_receipt", kwargs={"pk": order.pk}),
            follow=True,
        )
        order.refresh_from_db()
        self.assertRedirects(
            response,
            reverse("orders:order_detail", kwargs={"pk": order.pk}),
            fetch_redirect_response=False,
        )
        self.assertEqual(order.status, Order.OrderStatus.COMPLETED)
        self.assertContains(response, "已确认收货，交易完成")

    def test_seller_or_other_user_cannot_confirm_receipt(self):
        for username in ["收货视图卖家", "收货视图路人"]:
            order = self._create_order()
            self.client.login(username=username, password="testpass123")
            response = self.client.post(reverse("orders:order_confirm_receipt", kwargs={"pk": order.pk}))
            order.refresh_from_db()
            self.assertIn(response.status_code, [302, 404])
            self.assertEqual(order.status, Order.OrderStatus.AWAITING_RECEIPT)
            self.client.logout()
